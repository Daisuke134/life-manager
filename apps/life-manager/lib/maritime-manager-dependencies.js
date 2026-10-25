"use strict";

const { createMaritimeManagerPersistence } = require("./maritime-manager-persistence.js");
const { createMaritimeManagerStore } = require("./maritime-manager-store.js");
const { createAgentMailMailboxProvider, createMaritimeManagerMailboxStore } = require("./maritime-manager-mailbox.js");

function createMaritimeManagerDependencies({ pgPool, env = process.env } = {}) {
  if (!pgPool || typeof pgPool.query !== "function") throw new Error("maritime_manager_dependencies_unconfigured");
  const managerPersistence = createMaritimeManagerPersistence({ pgPool, env });
  const managerMailboxStore = createMaritimeManagerMailboxStore({
    query: pgPool.query.bind(pgPool),
    provider: createAgentMailMailboxProvider({ apiKey: env.LM_AGENTMAIL_API_KEY }),
  });
  return Object.freeze({
    query: pgPool.query.bind(pgPool),
    managerStore: createMaritimeManagerStore({ pgPool, env }),
    managerMailboxStore,
    managerPersistence,
    distributionStore: managerPersistence,
    ensureWebUserImpl: managerPersistence.ensureWebUserImpl,
    storeFirstTouch: managerPersistence.storeFirstTouch,
    readFirstTouch: managerPersistence.readFirstTouch,
    readFirstCompletedWorkAt: managerPersistence.readFirstCompletedWorkAt,
    cfoReceiptIO: managerPersistence.cfoReceiptIO,
  });
}

module.exports = { createMaritimeManagerDependencies };
