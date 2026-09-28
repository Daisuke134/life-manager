/** Base public RPC currently accepts eth_getLogs ranges of at most 2,000 blocks. */
export const BASE_LOG_CHUNK_SIZE = 2_000;

export function chunkBlockRanges(fromBlock, toBlock, chunkSize = BASE_LOG_CHUNK_SIZE) {
  if (!Number.isSafeInteger(fromBlock) || fromBlock < 0
    || !Number.isSafeInteger(toBlock) || toBlock < fromBlock) {
    throw new TypeError('block range invalid');
  }
  if (!Number.isSafeInteger(chunkSize) || chunkSize <= 0) {
    throw new TypeError('chunk size invalid');
  }
  const ranges = [];
  for (let start = fromBlock; start <= toBlock; start += chunkSize) {
    ranges.push([start, Math.min(start + chunkSize - 1, toBlock)]);
  }
  return ranges;
}
