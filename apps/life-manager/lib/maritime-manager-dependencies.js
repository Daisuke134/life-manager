"use strict";

const { createMaritimeManagerPersistence } = require("./maritime-manager-persistence.js");
const { createMaritimeManagerStore } = require("./maritime-manager-store.js");

function createMaritimeManagerDependencies({ pgPool, env = process.env } = {}) {
  if (!pgPool || typeof pgPool.query !== "function") throw new Error("maritime_manager_dependencies_unconfigured");
  const managerPersistence = createMaritimeManagerPersistence({ pgPool, env });
  return Object.freeze({
    managerStore: createMaritimeManagerStore({ pgPool, env }),
    managerPersistence,
    distributionStore: managerPersistence,
    ensureWebUserImpl: managerPersistence.ensureWebUserImpl,
    storeFirstTouch: managerPersistence.storeFirstTouch,
    readFirstTouch: managerPersistence.readFirstTouch,
    cfoReceiptIO: managerPersistence.cfoReceiptIO,
  });
}

module.exports = { createMaritimeManagerDependencies };
