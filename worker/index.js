const OWNER = 'joaoaravechia';
const REPO = 'cvm-scraper';
const WORKFLOW_FILE = 'scraper.yml';
const ALLOWED_ORIGIN = 'https://joaoaravechia.github.io';

function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const allowed = origin === ALLOWED_ORIGIN || origin === 'http://localhost:3000';
  return {
    'Access-Control-Allow-Origin': allowed ? origin : ALLOWED_ORIGIN,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

async function ghFetch(path, env, options = {}) {
  return fetch(`https://api.github.com${path}`, {
    headers: {
      'Authorization': `Bearer ${env.GITHUB_PAT}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'cvm-scraper-worker',
    },
    ...options,
  });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    const url = new URL(request.url);
    const headers = corsHeaders(request);
    headers['Content-Type'] = 'application/json';

    try {
      // POST /dispatch — dispara o workflow
      if (url.pathname === '/dispatch' && request.method === 'POST') {
        const body = await request.json();
        const res = await ghFetch(
          `/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
          env,
          {
            method: 'POST',
            body: JSON.stringify({
              ref: 'main',
              inputs: {
                competencia: body.competencia || '',
                cnpjs: body.cnpjs || '',
              },
            }),
          }
        );

        if (!res.ok) {
          const err = await res.text();
          return new Response(JSON.stringify({ error: err }), { status: res.status, headers });
        }
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
      }

      // GET /runs — lista runs recentes
      if (url.pathname === '/runs' && request.method === 'GET') {
        const res = await ghFetch(
          `/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=5`,
          env
        );
        const data = await res.json();
        const runs = (data.workflow_runs || []).map(r => ({
          id: r.id,
          status: r.status,
          conclusion: r.conclusion,
          created_at: r.created_at,
          html_url: r.html_url,
        }));
        return new Response(JSON.stringify({ runs }), { status: 200, headers });
      }

      // GET /runs/:id — status de uma run específica
      if (url.pathname.startsWith('/runs/') && request.method === 'GET') {
        const runId = url.pathname.split('/')[2];
        const res = await ghFetch(`/repos/${OWNER}/${REPO}/actions/runs/${runId}`, env);
        const run = await res.json();
        return new Response(JSON.stringify({
          id: run.id,
          status: run.status,
          conclusion: run.conclusion,
          html_url: run.html_url,
        }), { status: 200, headers });
      }

      // GET /artifacts/:runId — lista artifacts de uma run
      if (url.pathname.startsWith('/artifacts/') && request.method === 'GET') {
        const runId = url.pathname.split('/')[2];
        const res = await ghFetch(`/repos/${OWNER}/${REPO}/actions/runs/${runId}/artifacts`, env);
        const data = await res.json();
        const artifacts = (data.artifacts || []).map(a => ({
          id: a.id,
          name: a.name,
          size_in_bytes: a.size_in_bytes,
          download_url: `https://github.com/${OWNER}/${REPO}/actions/runs/${runId}`,
        }));
        return new Response(JSON.stringify({ artifacts }), { status: 200, headers });
      }

      return new Response(JSON.stringify({ error: 'Not found' }), { status: 404, headers });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), { status: 500, headers });
    }
  },
};
