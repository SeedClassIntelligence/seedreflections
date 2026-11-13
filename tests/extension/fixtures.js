// Pages that copy the structure each service uses today. They are approximations written for testing,
// not captures of the live sites, so passing them proves the reader logic, not the live layouts.
module.exports = {
  chatgpt: { host: 'chatgpt.com', path: '/c/6a1b2c3d-1111-2222-3333-444455556666', title: 'Pricing plan | ChatGPT', html: `
    <main><article><div data-message-author-role="user"><div>What should the beta pricing be?</div></div></article>
    <article><div data-message-author-role="assistant"><div><p>Start at $19 a month.</p><p>Offer a free tier.</p></div></div></article>
    <article><div data-message-author-role="tool">hidden tool output</div></article>
    <article><div data-message-author-role="user">Why three tiers?</div></article></main>` },
  claude: { host: 'claude.ai', path: '/chat/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', title: 'Launch checklist - Claude', html: `
    <div><div data-testid="user-message"><p>Draft a launch checklist.</p></div>
    <div class="font-claude-response"><div class="font-claude-response"><p>1. Terms page</p></div><p>2. Billing</p></div>
    <div data-testid="user-message">Add hosting.</div></div>` },
  gemini: { host: 'gemini.google.com', path: '/app/abc123def456', title: 'Google Gemini', html: `
    <user-query><div class="query-text">Plan my launch week</div></user-query>
    <model-response><message-content><p>Monday: terms.</p><p>Tuesday: hosting.</p></message-content></model-response>` },
  empty: { host: 'chatgpt.com', path: '/', title: 'ChatGPT', html: '<main><div>Welcome</div></main>' },
  other: { host: 'example.com', path: '/c/abcdef123456', title: 'Example', html: '<div data-message-author-role="user">hi</div>' }
};
