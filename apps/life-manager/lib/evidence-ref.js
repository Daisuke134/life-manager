"use strict";

const REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/?#-]{1,512}$/iu;
const SECRET_REF = /(?:password|cookie|api[_ -]?key|access[_ -]?token|secret|private[_ -]?key)/iu;
const LOCAL_PATH_REF = /(?:^|[/:])(?:Users|home|private|tmp|var)(?:[/:]|$)/u;

function validateEvidenceRefs(value, label = "evidence_refs", { min = 0, max = 64 } = {}) {
  if (!Array.isArray(value) || value.length < min || value.length > max) {
    throw new Error(`${label} invalid`);
  }
  const checked = value.map((item) => {
    if (typeof item !== "string" || !REF.test(item) || item.includes("@")
      || item.toLowerCase().startsWith("file://") || SECRET_REF.test(item)
      || LOCAL_PATH_REF.test(item)) {
      throw new Error(`${label} invalid`);
    }
    return item;
  });
  if (new Set(checked).size !== checked.length) throw new Error(`${label} duplicate`);
  return Object.freeze(checked);
}

module.exports = { validateEvidenceRefs };
