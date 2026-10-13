#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const { importContentObject, resolveContentObject } = require("../lib/content-object-store.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");

const HASH = /^[0-9a-f]{64}$/;
const APPLE_CAMPAIGNS = Object.freeze({
  "anicca-ios": Object.freeze({ app_id: "6755129214", token: /^anicca-ios_[A-Za-z0-9_-]{1,19}$/ }),
  "honne-ai": Object.freeze({ app_id: "6759667221", token: /^honne_en_(?:base|hook)_[a-z0-9_]+$/ }),
});

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function readReceipts(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8").split("\n").filter(Boolean).map(JSON.parse);
}

function platformOf(snapshot) {
  if (snapshot.kind === "tiktok_combined_metric_snapshot") return "tiktok";
  if (snapshot.kind === "instagram_combined_metric_snapshot") return "instagram";
  throw new Error(`unsupported metric snapshot kind: ${snapshot.kind}`);
}

function exactPublications(snapshot, receipts) {
  const platform = platformOf(snapshot);
  return receipts.filter(({ receipt }) => receipt
    && receipt.kind === "marketing_video_distribution"
    && receipt.status === "published"
    && receipt.product_id === snapshot.product_id
    && receipt.locale === snapshot.locale
    && receipt.platform === platform
    && receipt.provider_post_id === snapshot.provider_post_id
    && receipt.public_url === snapshot.public_url);
}

function appleCampaignLink(caption, productId) {
  const link = caption.split(/\s+/).map((value) => { try { const url = new URL(value); return url.protocol === "https:" && url.hostname === "apps.apple.com" ? url : null; } catch { return null; } }).find(Boolean);
  if (!link) return { campaign_url: null, campaign_id: null, campaign_status: "unavailable", campaign_reason: "campaign_not_configured" };
  const token = String(link.searchParams.get("ct") || "");
  const config = APPLE_CAMPAIGNS[productId];
  if (!token || !config?.token.test(token)) return { campaign_url: null, campaign_id: null, campaign_status: "invalid_for_product", campaign_reason: token ? "campaign_token_product_mismatch" : "campaign_token_missing" };
  if (!link.pathname.split("/").includes(`id${config.app_id}`)) return { campaign_url: null, campaign_id: null, campaign_status: "invalid_for_product", campaign_reason: "campaign_app_id_mismatch" };
  return { campaign_url: link.href, campaign_id: token, campaign_status: "configured", campaign_reason: "campaign_link_configured_no_product_readback" };
}

function exactCaption(receipt, productId, objectDir) {
  const digest = String(receipt.caption_sha256 || "");
  if (!HASH.test(digest)) throw new Error("publication caption hash is invalid");
  const ref = `object://sha256/${digest}`;
  const caption = fs.readFileSync(resolveContentObject(ref, { objectDir }), "utf8");
  const hook = caption.split(/\r?\n/).map((line) => line.trim()).find(Boolean);
  if (!hook) throw new Error("publication caption has no hook line");
  const campaign = appleCampaignLink(caption, productId);
  return {
    caption_ref: ref,
    hook_text: hook,
    hook_sha256: crypto.createHash("sha256").update(hook).digest("hex"),
    ...campaign,
  };
}

function buildLineage({ dataDir, tenantId = "dais-local" }) {
  const objectDir = path.join(dataDir, "objects");
  const metricsDir = path.join(dataDir, "tenants", tenantId, "marketing", "metrics");
  const metricFiles = [];
  if (fs.existsSync(metricsDir)) {
    for (const account of fs.readdirSync(metricsDir, { withFileTypes: true })) {
      if (!account.isDirectory()) continue;
      for (const post of fs.readdirSync(path.join(metricsDir, account.name), { withFileTypes: true })) {
        if (!post.isDirectory()) continue;
        const file = path.join(metricsDir, account.name, post.name, "24h.combined.json");
        if (fs.statSync(file, { throwIfNoEntry: false })?.isFile()) metricFiles.push(file);
      }
    }
  }
  metricFiles.sort();
  if (!metricFiles.length) return {
    schema_version: 1,
    kind: "marketing_attribution_lineage",
    tenant_id: tenantId,
    observed_at: null,
    rows: [],
    coverage: {
      included: 0,
      exact_publication_lineage: 0,
      campaign_attributed: 0,
      unattributed: 0,
      unprovable: 0,
      attribution_rate: null,
      attribution_rate_status: "unavailable",
      attribution_rate_reason: "no_24h_combined_metric_snapshots",
    },
  };
  const receipts = readReceipts(path.join(dataDir, "marketing", "receipts.jsonl"));
  const rows = metricFiles.map((file) => {
    const snapshot = readJson(file);
    const matches = exactPublications(snapshot, receipts);
    const metricObject = importContentObject(file, { objectDir });
    if (matches.length !== 1) return {
      publication_match_status: "unprovable",
      publication_match_count: matches.length,
      attribution_status: "unprovable",
      attribution_reason: matches.length ? "publication_receipt_ambiguous" : "publication_receipt_missing",
      product_id: snapshot.product_id,
      locale: snapshot.locale,
      platform: platformOf(snapshot),
      account_id: snapshot.account_id,
      integration_id: snapshot.integration_id,
      provider_post_id: snapshot.provider_post_id,
      public_url: snapshot.public_url,
      campaign_id: null,
      campaign_url: null,
      campaign_status: "unavailable",
      creative_id: null,
      slot: null,
      published_at: null,
      video_ref: null,
      caption_ref: null,
      hook_text: null,
      hook_sha256: null,
      metric_snapshot_ref: metricObject.ref,
      observed_at: snapshot.observed_at,
      window: snapshot.window,
    };
    const publication = matches[0].receipt;
    const caption = exactCaption(publication, snapshot.product_id, objectDir);
    const videoRef = `object://sha256/${publication.video_sha256}`;
    resolveContentObject(videoRef, { objectDir });
    return {
      publication_match_status: "exact",
      publication_match_count: 1,
      attribution_status: caption.campaign_id ? "partial" : "unattributed",
      attribution_reason: caption.campaign_reason,
      product_id: snapshot.product_id,
      locale: snapshot.locale,
      platform: platformOf(snapshot),
      account_id: snapshot.account_id,
      integration_id: snapshot.integration_id,
      provider_post_id: snapshot.provider_post_id,
      public_url: snapshot.public_url,
      campaign_id: caption.campaign_id,
      campaign_url: caption.campaign_url,
      campaign_status: caption.campaign_status,
      creative_id: publication.creative_id,
      slot: publication.slot,
      published_at: publication.published_at,
      video_ref: videoRef,
      ...caption,
      metric_snapshot_ref: metricObject.ref,
      observed_at: snapshot.observed_at,
      window: snapshot.window,
    };
  });
  const unprovable = rows.filter((row) => row.attribution_status === "unprovable").length;
  const rateReason = unprovable ? "publication_lineage_incomplete"
    : rows.some((row) => row.campaign_id) ? "campaign_link_configured_no_product_readback" : "campaign_not_configured";
  return {
    schema_version: 1,
    kind: "marketing_attribution_lineage",
    tenant_id: tenantId,
    observed_at: rows.map((row) => row.observed_at).sort().at(-1),
    rows,
    coverage: {
      included: rows.length,
      exact_publication_lineage: rows.filter((row) => row.publication_match_status === "exact").length,
      campaign_attributed: 0,
      unattributed: rows.filter((row) => row.attribution_status === "unattributed").length,
      unprovable,
      attribution_rate: null,
      attribution_rate_status: "unavailable",
      attribution_rate_reason: rateReason,
    },
  };
}

function persistLineage({ dataDir, tenantId = "dais-local" }) {
  const lineage = buildLineage({ dataDir, tenantId });
  const directory = path.join(dataDir, "tenants", tenantId, "marketing", "attribution");
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const candidate = path.join(directory, `.lineage-${process.pid}.json`);
  fs.writeFileSync(candidate, `${JSON.stringify(lineage, null, 2)}\n`, { mode: 0o600 });
  const imported = importContentObject(candidate, { objectDir: path.join(dataDir, "objects") });
  fs.unlinkSync(candidate);
  const pointer = path.join(directory, "lineage.json");
  const previous = fs.statSync(pointer, { throwIfNoEntry: false })?.isFile() ? readJson(pointer) : null;
  const value = { ...lineage, snapshot_ref: imported.ref };
  const temporary = `${pointer}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, pointer);
  return { created: previous?.snapshot_ref !== imported.ref, pointer, ...value };
}

if (require.main === module) {
  const result = persistLineage({ dataDir: resolveDataRoot(process.env) });
  process.stdout.write(`${JSON.stringify({
    created: result.created,
    snapshot_ref: result.snapshot_ref,
    included: result.coverage.included,
    exact_publication_lineage: result.coverage.exact_publication_lineage,
    campaign_attributed: result.coverage.campaign_attributed,
    unattributed: result.coverage.unattributed,
    pointer: result.pointer,
  })}\n`);
}

module.exports = { buildLineage, persistLineage };
