#!/usr/bin/env node
/**
 * Publish one existing MP4 through an already-authenticated TikTok Studio browser.
 *
 * The adapter deliberately preserves postiz_video.py's terminal JSON contract so the
 * distribution orchestrator can change adapters without changing creative semantics.
 */

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { pathToFileURL } from "node:url";


export const POSTIZ_EQUIVALENCE_FIELDS = ["state", "post_url", "post_id"];
const PUBLIC_VIDEO = /^https:\/\/www\.tiktok\.com\/@[^/]+\/video\/[0-9]+\/?$/;
const UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center";


export class TikTokDirectError extends Error {}


export function validatePublicVideoUrl(value) {
  return typeof value === "string" && PUBLIC_VIDEO.test(value);
}


export function classifyUploadPage(url, bodyText, fileInputCount) {
  if (String(url).includes("/login")) return "authentication_required";
  if (/本人確認|verify your identity|verification code/i.test(String(bodyText))) {
    return "verification_required";
  }
  return Number(fileInputCount) > 0 ? "ready" : "upload_unavailable";
}


export function buildPublishedResult(url, postId) {
  if (!validatePublicVideoUrl(url) || !/^[0-9]+$/.test(String(postId))) {
    throw new TikTokDirectError("TikTok did not return an individual public video URL");
  }
  return {
    state: "PUBLISHED",
    post_url: url,
    post_id: String(postId),
    route: "direct_browser",
    provider_cost_usd: 0,
  };
}


function normalized(value) {
  return String(value).replace(/\s+/g, " ").trim().toLocaleLowerCase();
}


export function loggedOutReadback(url, caption, runner = spawnSync) {
  if (!validatePublicVideoUrl(url)) return false;
  const result = runner("yt-dlp", ["--dump-single-json", "--no-warnings", url], {
    encoding: "utf8",
    timeout: 60_000,
  });
  if (result.status !== 0) return false;
  let row;
  try {
    row = JSON.parse(result.stdout);
  } catch {
    return false;
  }
  const expectedId = url.match(/\/video\/([0-9]+)/)?.[1];
  const providerUrl = row.webpage_url || row.original_url || "";
  const providerCaption = row.description || row.title || "";
  return (
    String(row.id) === expectedId
    && validatePublicVideoUrl(providerUrl)
    && providerUrl.match(/\/video\/([0-9]+)/)?.[1] === expectedId
    && normalized(providerCaption) === normalized(caption)
  );
}


function jstDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}


export async function exactContract(videoPath, captionPath) {
  const [video, rawCaption] = await Promise.all([readFile(videoPath), readFile(captionPath, "utf8")]);
  const caption = rawCaption.trim();
  if (video.length === 0 || caption.length === 0) {
    throw new TikTokDirectError("video and caption must be non-empty");
  }
  return {
    video_sha256: createHash("sha256").update(video).digest("hex"),
    caption_sha256: createHash("sha256").update(rawCaption).digest("hex"),
    caption,
  };
}


function validMigrationRow(row) {
  return (
    row
    && /^\d{4}-\d{2}-\d{2}$/.test(row.date)
    && row.route === "direct_browser"
    && validatePublicVideoUrl(row.public_url)
    && row.logged_out_readback === true
    && row.provider_cost_usd === 0
    && row.simulated !== true
  );
}


export function directMigrationStatus(rows) {
  const byDate = new Map();
  for (const row of rows) {
    if (validMigrationRow(row) && !byDate.has(row.date)) byDate.set(row.date, row);
  }
  const dates = [...byDate.keys()].sort();
  if (dates.length === 0) return { status: "pending", day_index: 0, streak_dates: [] };
  let streak = [dates.at(-1)];
  for (let index = dates.length - 2; index >= 0; index -= 1) {
    const newer = Date.parse(`${streak[0]}T00:00:00Z`);
    const older = Date.parse(`${dates[index]}T00:00:00Z`);
    if (newer - older !== 86_400_000) break;
    streak.unshift(dates[index]);
  }
  const done = streak.length >= 2;
  return {
    status: done ? "done" : "started",
    day_index: done ? 2 : 1,
    streak_dates: streak.slice(-2),
  };
}


function argument(name, argv) {
  const index = argv.indexOf(name);
  return index >= 0 ? argv[index + 1] : undefined;
}


async function findPublishedLink(page) {
  const link = page.locator('a[href*="/video/"]').first();
  await link.waitFor({ state: "visible", timeout: 120_000 });
  const href = await link.getAttribute("href");
  if (!href) throw new TikTokDirectError("publish confirmation has no public URL");
  return href.startsWith("http") ? href : new URL(href, "https://www.tiktok.com").toString();
}


export async function runDirect({
  video,
  captionFile,
  cdpUrl = "http://localhost:9222",
  preflight = false,
}) {
  const contract = await exactContract(video, captionFile);
  const { chromium } = await import("playwright-core");
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0];
  if (!context) throw new TikTokDirectError("CDP browser has no persistent context");
  const page = await context.newPage();
  try {
    await page.goto(UPLOAD_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
    const fileInput = page.locator('input[type="file"]').first();
    let pageState = classifyUploadPage(
      page.url(),
      await page.locator("body").innerText().catch(() => ""),
      await fileInput.count(),
    );
    if (pageState === "upload_unavailable") {
      await fileInput.waitFor({ state: "attached", timeout: 30_000 }).catch(() => {});
      pageState = classifyUploadPage(
        page.url(),
        await page.locator("body").innerText().catch(() => ""),
        await fileInput.count(),
      );
    }
    if (pageState !== "ready") throw new TikTokDirectError(pageState);
    if (preflight) {
      return {
        state: "READY",
        route: "direct_browser",
        provider_cost_usd: 0,
        ...contract,
      };
    }

    await fileInput.setInputFiles(video);
    const textboxes = page.getByRole("textbox");
    await textboxes.first().waitFor({ state: "visible", timeout: 120_000 });
    const count = await textboxes.count();
    let captionBox = null;
    for (let index = 0; index < count; index += 1) {
      const candidate = textboxes.nth(index);
      const editable = await candidate.getAttribute("contenteditable");
      const multiline = await candidate.getAttribute("aria-multiline");
      if (editable === "true" || multiline === "true") {
        captionBox = candidate;
        break;
      }
    }
    if (!captionBox) throw new TikTokDirectError("TikTok caption textbox is unavailable");
    await captionBox.fill(contract.caption);

    const aiText = page.getByText(/AI生成|AI-generated|AIGC/i).first();
    await aiText.waitFor({ state: "visible", timeout: 30_000 });
    const aiContainer = aiText.locator("xpath=ancestor::*[@role='switch' or @role='checkbox'][1]");
    if (await aiContainer.count()) {
      if ((await aiContainer.getAttribute("aria-checked")) !== "true") await aiContainer.click();
    } else {
      const checkbox = aiText.locator("xpath=ancestor::*[1]").getByRole("checkbox");
      if (!(await checkbox.count())) throw new TikTokDirectError("AI disclosure control is unavailable");
      if (!(await checkbox.isChecked())) await checkbox.check();
    }

    const publish = page.getByRole("button", { name: /^(投稿|Post)$/i });
    await publish.waitFor({ state: "visible", timeout: 120_000 });
    if (await publish.isDisabled()) throw new TikTokDirectError("TikTok publish button is disabled");
    await publish.click();
    const publicUrl = await findPublishedLink(page);
    const postId = publicUrl.match(/\/video\/([0-9]+)/)?.[1];
    if (!loggedOutReadback(publicUrl, contract.caption)) {
      throw new TikTokDirectError("logged_out_readback_failed");
    }
    return {
      ...buildPublishedResult(publicUrl, postId),
      ...contract,
      logged_out_readback: true,
      migration_date: jstDate(),
    };
  } finally {
    await page.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}


async function main(argv) {
  const video = argument("--video", argv);
  const captionFile = argument("--caption-file", argv);
  if (!video || !captionFile) throw new TikTokDirectError("--video and --caption-file are required");
  const result = await runDirect({
    video,
    captionFile,
    cdpUrl: argument("--cdp-url", argv) || process.env.LM_TIKTOK_CDP_URL,
    preflight: argv.includes("--preflight"),
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}


if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch((error) => {
    process.stdout.write(`${JSON.stringify({ state: "ERROR", error: error.message })}\n`);
    process.exitCode = 1;
  });
}
