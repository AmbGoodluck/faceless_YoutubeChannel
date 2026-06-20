// Cloudflare Worker — catches Slack "Approve" button clicks and triggers the next
// GitHub Actions stage. Deploy with: wrangler deploy
//
// Secrets (wrangler secret put NAME):
//   SLACK_SIGNING_SECRET   - from your Slack app's Basic Information
//   GH_TOKEN               - GitHub fine-grained PAT with Actions: read+write on the repo
// Vars (in wrangler.toml [vars]):
//   GH_OWNER, GH_REPO, WORKFLOW_FILE (e.g. "pipeline.yml")

async function verifySlack(req, bodyText, secret) {
  const ts = req.headers.get("x-slack-request-timestamp");
  const sig = req.headers.get("x-slack-signature");
  if (!ts || !sig) return false;
  if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) return false; // replay guard
  const base = `v0:${ts}:${bodyText}`;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(base));
  const hex = [...new Uint8Array(mac)].map(b => b.toString(16).padStart(2, "0")).join("");
  return `v0=${hex}` === sig;
}

async function dispatch(env, stage, episode) {
  const url = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  return fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "lights-out-approver",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { stage, episode } }),
  });
}

export default {
  async fetch(req, env) {
    if (req.method !== "POST") return new Response("ok");
    const bodyText = await req.text();
    if (!(await verifySlack(req, bodyText, env.SLACK_SIGNING_SECRET)))
      return new Response("bad signature", { status: 401 });

    const params = new URLSearchParams(bodyText);
    const payload = JSON.parse(params.get("payload") || "{}");
    const action = payload.actions && payload.actions[0];
    if (!action) return new Response("no action");

    const [verb, episode] = (action.value || "").split(":");
    if (action.action_id === "reject")
      return Response.json({ replace_original: true, text: `⏭️ Skipped ${episode}.` });

    // verb is the NEXT stage to run: "render" or "publish"
    await dispatch(env, verb, episode);
    return Response.json({
      replace_original: true,
      text: `✅ Approved — running *${verb}* for \`${episode}\`. You'll get the next update here.`,
    });
  },
};
