import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { createHash } from "node:crypto";
import { PGlite } from "@electric-sql/pglite";

const snapshot = Buffer.from("SQLite format 3\0UNKNOWN reserved occurrence").toString("base64");
const sha256 = createHash("sha256").update(Buffer.from(snapshot, "base64")).digest("hex");
const first = "123456:1:e83be31d-a863-43b3-802b-40be9edee813";
const second = "123457:1:a59ac014-ef59-4b30-9c2d-18379834fd0d";

test("real PostgreSQL private checkpoint ownership and CAS", async t => {
  const db = new PGlite();
  try {
    await db.exec("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;");
    await db.exec(await readFile(new URL("../20261022_private_checkpoint.sql", import.meta.url), "utf8"));
    const call = async (operation, owner, revision = null, digest = null, data = null, role = "service_role") => {
      await db.exec(`SET ROLE ${role}`);
      try {
        return (await db.query("SELECT public.lm_manager_owned_checkpoint($1,$2,$3,$4,$5) AS value",
          [operation, owner, revision, digest, data])).rows[0].value;
      } finally { await db.exec("RESET ROLE"); }
    };
    const seed = async () => {
      await db.query("DELETE FROM public.lm_manager_owned_state");
      await db.query("INSERT INTO public.lm_manager_owned_state (stream,revision,sha256,snapshot) VALUES ('manager-owned-digital-v1',0,$1,$2)", [sha256, snapshot]);
    };
    const rejectsCode = async (promise, code) => assert.rejects(promise, error => error.code === code);

    await t.test("migration does not initialize missing runtime state", async () => {
      assert.equal((await db.query("SELECT count(*)::int AS count FROM public.lm_manager_owned_state")).rows[0].count, 0);
      await rejectsCode(call("acquire", first), "PT404");
    });
    await t.test("anonymous and authenticated roles cannot read state or invoke RPC", async () => {
      for (const role of ["anon", "authenticated"]) {
        await rejectsCode(call("acquire", first, null, null, null, role), "42501");
        await db.exec(`SET ROLE ${role}`);
        try { await rejectsCode(db.query("SELECT * FROM public.lm_manager_owned_state"), "42501"); }
        finally { await db.exec("RESET ROLE"); }
      }
      const row = (await db.query("SELECT relrowsecurity AS rls, relforcerowsecurity AS force FROM pg_class WHERE oid='public.lm_manager_owned_state'::regclass")).rows[0];
      assert.deepEqual(row, { rls: true, force: true });
    });
    await t.test("acquire sets a 15 minute lease without changing saved state", async () => {
      await seed();
      assert.deepEqual(await call("acquire", first), { revision: 0, sha256, snapshot, owner: first });
      const row = (await db.query("SELECT extract(epoch FROM lease_until-clock_timestamp())::int AS seconds FROM public.lm_manager_owned_state")).rows[0];
      assert.ok(row.seconds >= 890 && row.seconds <= 900);
      await rejectsCode(call("acquire", first), "PT409");
      await rejectsCode(call("acquire", second), "PT409");
    });
    await t.test("checkpoint requires exact active owner, revision, and calculated digest", async () => {
      const next = Buffer.from("SQLite format 3\0UNKNOWN reserved occurrence plus receipt").toString("base64");
      const digest = createHash("sha256").update(Buffer.from(next, "base64")).digest("hex");
      await rejectsCode(call("checkpoint", second, 0, digest, next), "PT409");
      await rejectsCode(call("checkpoint", first, 1, digest, next), "PT409");
      await rejectsCode(call("checkpoint", first, 0, "b".repeat(64), next), "PT400");
      const value = await call("checkpoint", first, 0, digest, next);
      assert.deepEqual(value, { revision: 1, sha256: digest, snapshot: next, owner: first });
      // A response-lost caller cannot replay its old CAS as a fresh save.
      await rejectsCode(call("checkpoint", first, 0, digest, next), "PT409");
    });
    await t.test("expired owner cannot save; next owner restores the reserved checkpoint", async () => {
      await db.query("UPDATE public.lm_manager_owned_state SET lease_until=clock_timestamp()-interval '1 second'");
      const expected = (await db.query("SELECT revision::int,sha256,snapshot FROM public.lm_manager_owned_state")).rows[0];
      await rejectsCode(call("checkpoint", first, expected.revision, expected.sha256, expected.snapshot), "PT409");
      assert.deepEqual(await call("acquire", second), { ...expected, owner: second });
      await rejectsCode(call("release", first), "PT409");
    });
    await t.test("release retains all journal bytes and revision", async () => {
      const expected = (await db.query("SELECT revision::int,sha256,snapshot FROM public.lm_manager_owned_state")).rows[0];
      assert.deepEqual(await call("release", second), { ...expected, owner: null });
      assert.equal((await db.query("SELECT lease_until FROM public.lm_manager_owned_state")).rows[0].lease_until, null);
    });
    await t.test("disaster recovery marker blocks acquire and checkpoint without erasing state", async () => {
      await call("acquire", first);
      await db.query("UPDATE public.lm_manager_owned_state SET recovery_required=true");
      await rejectsCode(call("checkpoint", first, 1, sha256, snapshot), "PT409");
      await call("release", first);
      await rejectsCode(call("acquire", second), "PT409");
      assert.equal((await db.query("SELECT revision::int FROM public.lm_manager_owned_state")).rows[0].revision, 1);
    });
    await t.test("RPC rejects unexpected operation, bad owner, extra CAS fields, oversized bytes", async () => {
      await seed();
      await rejectsCode(call("initialize", first), "PT400");
      await rejectsCode(call("acquire", "forged"), "PT400");
      await rejectsCode(call("acquire", first, 0), "PT400");
      await call("acquire", first);
      await rejectsCode(call("checkpoint", first, 0, sha256, `${snapshot}\n`), "PT400");
      await rejectsCode(call("checkpoint", first, 0, sha256, Buffer.alloc(1048577).toString("base64")), "PT400");
    });
  } finally { await db.close(); }
});
