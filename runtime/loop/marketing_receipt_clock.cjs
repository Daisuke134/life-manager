"use strict";

const fs = require("node:fs");
const readline = require("node:readline");
const { verifyMarketingDailyReceipt } = require("../../apps/life-manager/lib/marketing-daily-adapter.js");
const { verifyMarketingVideoPublicationReceipt } = require("../../apps/life-manager/lib/marketing-video-publication-adapter.js");
const { verifyMarketingNativeCarouselPublicationReceipt } = require("../../apps/life-manager/lib/marketing-native-carousel-publication-adapter.js");

async function main() {
  const [file, product, now] = process.argv.slice(2);
  let latest = null;
  const validators = [verifyMarketingDailyReceipt, verifyMarketingVideoPublicationReceipt,
    verifyMarketingNativeCarouselPublicationReceipt];
  const lines = readline.createInterface({ input: fs.createReadStream(file), crlfDelay: Infinity });
  for await (const line of lines) {
    try {
      const receipt = JSON.parse(line)?.receipt;
      if (!receipt || (receipt.product_id || receipt.product) !== product
          || receipt.provider_reconciled !== true || !receipt.provider_post_id) continue;
      const verified = validators.some(validate => {
        try { return validate(receipt); } catch { return false; }
      });
      const stamp = Date.parse(receipt.published_at);
      if (verified && Number.isFinite(stamp) && stamp <= Number(now) * 1000
          && (latest === null || stamp > Date.parse(latest))) latest = receipt.published_at;
    } catch { /* One malformed receipt cannot hide another product's outcome. */ }
  }
  process.stdout.write(JSON.stringify({ last_verified_outcome: latest }));
}

main().catch(() => { process.exitCode = 1; });
