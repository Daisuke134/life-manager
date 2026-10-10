import os, json, urllib.request, uuid, datetime, pathlib

KEY = os.environ["LM_POSTIZ_API_KEY"]
IID = os.environ["CAPAFY_IG_POSTIZ_INTEGRATION_ID"]
B = pathlib.Path.home() / ".local/state/life-manager/marketing/capafy-videos"
import sys
ITEMS = json.load(open(sys.argv[1]))


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers={"Authorization": KEY, **(headers or {})}, method=method)
    return json.load(urllib.request.urlopen(r, timeout=180))


for it in ITEMS:
    slug, date, body, tags, URL, NAME = it["slug"], it["date"], it["body"], it["tags"], it["url"], it["name"]
    receipts = B / slug / "postiz-receipts.jsonl"
    if receipts.exists():
        print(slug, "already has receipt; skip")
        continue
    mp4 = B / slug / "renders/video.mp4"
    bnd = uuid.uuid4().hex
    data = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{slug}.mp4\"\r\n"
            f"Content-Type: video/mp4\r\n\r\n").encode() + mp4.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
    up = req("https://api.postiz.com/public/v1/upload", data, {"Content-Type": f"multipart/form-data; boundary={bnd}"}, "POST")
    content = f"{body}\n\nTry it on Capafy: {URL}\n(or search \"{NAME}\" on Capafy)\n\n{tags}"
    payload = {"type": "schedule", "date": date, "shortLink": False, "tags": [],
               "posts": [{"integration": {"id": IID},
                          "value": [{"content": content, "image": [{"id": up["id"], "path": up["path"]}]}],
                          "settings": {"__type": "instagram-standalone", "post_type": "post",
                                       "is_trial_reel": False, "collaborators": []}}]}
    cr = req("https://api.postiz.com/public/v1/posts", json.dumps(payload).encode(), {"Content-Type": "application/json"}, "POST")
    rec = {"at": datetime.datetime.now().isoformat(), "integration": "capafy.hooklab", "asset": str(mp4),
           "upload": up, "create": cr, "scheduled_for": date}
    with receipts.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(slug, date, json.dumps(cr)[:160])
