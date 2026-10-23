# Lancers on your Mac

[Get started](getting-started.md) · [Agent catalog](agents.md)

Connect your own Lancers account to find suitable work, handle replies and paid tasks,
and keep track of results. You need ChatGPT Plus or higher and a Mac that stays awake.
End-to-end acceptance on a separate clean Mac remains open.

## Prepare your work profile

Create a JSON file with your name and facts you can support with evidence. For example:

```json
{
  "version": 1,
  "candidate": {"name": "Your name"},
  "facts": [
    {
      "id": "project-1",
      "claim": "Describe work you have actually done.",
      "evidence": "A link or reference that supports this claim."
    }
  ]
}
```

Replace the example with your own facts. Age, nationality and a portfolio are not required
for this work profile. Keep this file outside the Git checkout.

## Install and connect

From your Life Manager checkout:

```bash
./install.sh lancers install --candidate-profile /absolute/path/to/work-profile.json
```

The installer prepares the Mac dependencies, asks you to sign in with ChatGPT when needed,
and prepares a Lancers browser window. Open <https://www.lancers.jp/mypage> in that window
and sign in with your own account. Complete any official verification, then run the same command again.
You do not need a separate OpenAI API key.

The installer checks the signed-in account again and starts only the work that has its
required setup. Missing storefront or report settings do not stop unrelated work.
It preserves existing private setup and confirmed listing IDs when you rerun it.
Conflicting inputs are reported rather than overwriting the existing setup.

## Optional: your storefront

To create or maintain your own listing, copy the
[storefront template](examples/lancers-storefront-product.json) outside the checkout.
Replace every placeholder with your service details and truthful project descriptions.
Use your own Lancers profile path, service image and avatar. Set your own prices and
the exact category names shown by Lancers. Leave new listing and portfolio IDs empty.
Use a 25–40 character service title stem without the final `ます`, a subtitle of at most
60 characters, and exactly three pricing plans. Replace the project durations and AI-use
flags with facts about your own work.

Calculate the image hashes with `shasum -a 256 avatar.png service.png` and fill in the
matching fields. Relative image paths are resolved from your product file's directory;
keep those source images on your Mac after importing.

```bash
./install.sh lancers install \
  --candidate-profile /absolute/path/to/work-profile.json \
  --product /absolute/path/to/storefront-product.json
```

An optional `--catalog /absolute/path/to/listing-catalog.json` imports your own shared
listing catalog. It is not needed for a single product. Templates are not ready-to-publish
service claims, and the installer does not fill them with the author's profile or work.

## Check setup and results

```bash
./install.sh lancers plan
./bin/lm-loop status lancers-revenue-application
```

`plan` checks local setup without signing in, changing files or starting agents.
`setup_required` lists what is missing. `waiting` means an existing owner still needs to
finish adopting the requested release. Installation alone does not mean that an application,
reply, sale or delivery succeeded; check the reported provider result.

For keeping the Mac awake or stopping an agent, use the
[Mac setup guide](getting-started.md).
