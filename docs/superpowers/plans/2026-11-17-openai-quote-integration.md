# Mangen OpenAI 智能询价接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `mangen.jp/quote` 中加入 OpenAI 询价理解能力，把任意微信询价原文转换为可校验的标准行程，并且只使用现有价格表自动计算金额。

**Architecture:** Cloudflare Pages Functions 在同域名后端调用 OpenAI Responses API；模型通过 Structured Outputs 返回固定 JSON，不返回价格。程序校验人数、车型容量、日期、服务类型和证据后，把安全的结构化项目交给现有 `QuoteEngine.getPrice()` 计价；API不可用时保留现有本地识别和手动报价。本计划只实现核心解析、访问保护、自动匹配和回退；脱敏反馈案例库与持续评估数据库另列后续计划。

**Tech Stack:** 静态 HTML/CSS/JavaScript、Cloudflare Pages Functions、OpenAI Responses API、Structured Outputs、Node.js 内置测试运行器

**Spec:** `docs/superpowers/specs/2026-09-27-ai-quote-parser-design.md`

## Global Constraints

- AI只理解询价，不得输出、推测或修改金额。
- 最终金额只来自 `assets/quote/price-data.js` 和 `QuoteEngine.getPrice()`。
- 无证据、存在冲突或报价表未覆盖的项目必须标黄或标红，不得自动计入合计。
- OpenAI API 密钥、访问码摘要和会话签名密钥只保存在 Cloudflare 环境变量中。
- 浏览器不得直接调用 OpenAI，也不得接触密钥。
- API失败、超时或拒绝时保留原文，并允许使用现有本地识别和手动录价。
- 单次询价原文最多 12,000 字符；后端请求超时 20 秒。
- 初始主模型为 `gpt-6-luna`；仅对程序发现的歧义使用 `gpt-6.1-sol` 针对性复核。两个模型均由环境变量覆盖。
- OpenAI 请求设置 `store: false`。
- 不在服务端日志中记录未脱敏询价原文。

## Review Focus

- “6名客人＋1名导游”必须得到总人数7并推荐海狮，不能把导游漏掉。
- “接机后游览”或“市内游览后送机”必须按组合/包车处理，不能套单次接送价。
- 同日同时出现成田和羽田必须进入人工确认，不能自动计价。
- API超时、结构不合法或模型拒绝时必须保留输入并可退回本地解析。
- 重复点击识别按钮只能产生一个在途请求，不能重复扣费。

---

### Task 1: 结构化询价契约、脱敏与确定性校验

**Files:**
- Create: `functions/_shared/quote-schema.mjs`
- Create: `functions/_shared/redact-inquiry.mjs`
- Create: `functions/_shared/validate-quote.mjs`
- Create: `tests/quote-ai-contract.test.mjs`

**Interfaces:**
- Produces: `QUOTE_SCHEMA`, `redactInquiry(text: string): string`, `validateNormalizedQuote(quote: object): { quote: object, validation_results: object[], review_questions: string[] }`
- Consumes: no application code.

- [ ] **Step 1: Write failing contract, redaction, and validation tests**

Add tests for schema enums and absence of price fields; phone/email/WeChat redaction; total people recomputation; 6+1 guide capacity warning; airport conflict; mixed charter/transfer; unknown service type; and missing evidence.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `node --test tests/quote-ai-contract.test.mjs`  
Expected: FAIL because the shared modules do not exist.

- [ ] **Step 3: Implement the three shared modules**

`QUOTE_SCHEMA` uses strict JSON Schema with required keys for language, passenger counts, requested vehicle, dates, daily services, evidence, confidence, and unresolved questions. It contains no price or amount property. `validateNormalizedQuote()` recalculates totals and derives green/yellow/red status from evidence and business conflicts rather than trusting model confidence alone.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `node --test tests/quote-ai-contract.test.mjs`  
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat: add quote AI contract and validator"`

### Task 2: 公司访问码与短期会话保护

**Files:**
- Create: `functions/_shared/session.mjs`
- Create: `functions/api/quote-auth.js`
- Create: `tests/quote-auth.test.mjs`

**Interfaces:**
- Produces: `createSession(env, now): Promise<string>`, `verifySession(token, env, now): Promise<boolean>`, POST `/api/quote-auth`.
- Consumes: Cloudflare secrets `QUOTE_ACCESS_CODE_HASH` and `QUOTE_SESSION_SECRET`.

- [ ] **Step 1: Write failing authentication tests**

Cover correct/incorrect access code, constant-time hash comparison, signed 30-day HttpOnly cookie, expiry, modified token, missing secrets, non-JSON request, and oversized input.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `node --test tests/quote-auth.test.mjs`  
Expected: FAIL because session and endpoint modules do not exist.

- [ ] **Step 3: Implement signed session and authentication endpoint**

Use Web Crypto SHA-256 and HMAC-SHA256. Return a `mangen_quote_session` cookie with `HttpOnly; Secure; SameSite=Strict; Path=/api; Max-Age=2592000`. Never return or log the access code.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `node --test tests/quote-auth.test.mjs`  
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat: protect quote AI endpoint with access code"`

### Task 3: OpenAI Responses API 客户端与解析端点

**Files:**
- Create: `functions/_shared/openai-quote.mjs`
- Create: `functions/api/parse-quote.js`
- Create: `tests/parse-quote-api.test.mjs`

**Interfaces:**
- Produces: `parseInquiryWithOpenAI({ text, env, fetchImpl, signal }): Promise<object>`, POST `/api/parse-quote`.
- Consumes: Task 1 schema/redaction/validator; Task 2 session verification; secrets `OPENAI_API_KEY`; optional `OPENAI_MODEL_PRIMARY`, `OPENAI_MODEL_REVIEW`.

- [ ] **Step 1: Write failing API and OpenAI-client tests**

Mock `fetch` and cover: valid Structured Output; `store:false`; strict `text.format`; model refusal; incomplete output; invalid schema; OpenAI 429/5xx; 20-second abort; unauthenticated call; input length limit; 6+1 guide; mixed airport/tour; dual-airport conflict.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `node --test tests/parse-quote-api.test.mjs`  
Expected: FAIL because the client and endpoint do not exist.

- [ ] **Step 3: Implement primary parsing call**

Call `POST https://api.openai.com/v1/responses` with the primary model, `reasoning.effort: "low"`, concise multilingual instructions, strict `QUOTE_SCHEMA`, `store:false`, and the redacted inquiry. Extract only the structured output.

- [ ] **Step 4: Implement targeted review and normalized API response**

Only when Task 1 validation reports supported ambiguity classes, call the review model with the specific issue and original evidence; never request or accept price fields. Return `normalized_quote`, `validation_results`, `review_questions`, `parse_id`, and safe model metadata.

- [ ] **Step 5: Run the tests and verify they pass**

Run: `node --test tests/parse-quote-api.test.mjs`  
Expected: PASS with no live network calls.

- [ ] **Step 6: Commit**

`git commit -m "feat: parse quote inquiries with OpenAI"`

### Task 4: 把 AI 结果接入现有报价页面

**Files:**
- Modify: `quote.html`
- Modify: `assets/quote/app.js`
- Modify: `assets/quote/styles.css`
- Create: `assets/quote/ai-quote-client.js`
- Create: `tests/quote-ai-ui.test.cjs`
- Modify: `tests/package.json`

**Interfaces:**
- Produces: `AIQuoteClient.authenticate(code)`, `AIQuoteClient.parse(text)`, `mapNormalizedQuoteToState(result, quoteEngine)`.
- Consumes: Task 2 and Task 3 endpoints; existing `QuoteEngine.getPrice()`, state renderer, vehicle selector, manual price flow, copy and print actions.

- [ ] **Step 1: Write failing browser/DOM tests**

Cover first-use access-code prompt; authenticated parsing; loading state; duplicate-click suppression; mapping dates/routes/services into rows; green-only automatic price lookup; yellow/red excluded from total; inline evidence/questions; API failure fallback button; preservation of input; successful retry.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd tests && npm test -- --test-name-pattern="AI quote"`  
Expected: FAIL because the AI client and UI states do not exist.

- [ ] **Step 3: Implement the browser client and mapping layer**

Keep the current local parser callable as fallback. The AI client sends only inquiry text and local timezone. Mapping converts allowed service enums to existing price keys; unknown or conflicting items become `manual` and never receive an automatic amount.

- [ ] **Step 4: Add compact review UI**

Show “AI识别中”, evidence, yellow/red questions, retry, and “使用本地识别” without redesigning the existing quote workspace. Do not change vehicle images, price data, copy output, or desktop print behavior.

- [ ] **Step 5: Run DOM and quote regression tests**

Run: `cd tests && npm test`  
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat: connect quote page to AI parser"`

### Task 5: 回归案例、部署说明与预览验收

**Files:**
- Create: `tests/fixtures/quote-ai-cases.json`
- Create: `tests/quote-ai-regression.test.mjs`
- Modify: `README.md`
- Modify: `docs-deploy.md`

**Interfaces:**
- Produces: versioned offline regression corpus and exact Cloudflare/OpenAI configuration instructions.
- Consumes: all prior tasks.

- [ ] **Step 1: Add at least 20 initial anonymized regression cases**

Include D1/D2 dates, range-plus-day-only dates, Chinese numerals, guides, vehicle aliases, airport pickup/dropoff, USJ round trip, mixed charter/transfer, dual airports, cross-region routes, VIP/formal attire/water, Japanese/Chinese mixed text, and irregular line breaks. Each case asserts normalized fields and whether automatic pricing is allowed.

- [ ] **Step 2: Run the regression suite**

Run: `node --test tests/quote-ai-regression.test.mjs`  
Expected: PASS using deterministic mocked model output and the real validator/price mapping.

- [ ] **Step 3: Document production configuration**

Document these Cloudflare secrets/variables without values: `OPENAI_API_KEY`, `QUOTE_ACCESS_CODE_HASH`, `QUOTE_SESSION_SECRET`, `OPENAI_MODEL_PRIMARY=gpt-6-luna`, `OPENAI_MODEL_REVIEW=gpt-6.1-sol`. Include key rotation, disabling the endpoint, and rollback to local parsing.

- [ ] **Step 4: Run the complete local suite**

Run: `python -m pytest tests -q && cd tests && npm test && cd .. && node --test tests/quote-*.test.mjs tests/parse-quote-api.test.mjs`  
Expected: all tests PASS.

- [ ] **Step 5: Deploy a Cloudflare preview and perform live smoke tests**

Verify desktop Safari/Chrome and mobile/WeChat-sized viewport: authentication, one simple quote, one ambiguous quote, local fallback, copy-to-WeChat, and no OpenAI key in HTML/network responses. Do not point production traffic to the preview.

- [ ] **Step 6: Commit**

`git commit -m "test: add AI quote regression coverage and deployment guide"`

## Self-review result

- Spec coverage for the requested production core is complete: fixed schema, redaction before OpenAI, deterministic validation, secure backend call, access protection, price-table-only amounts, review states, fallback, regression cases, and deployment configuration.
- Deliberately deferred to a separate plan: persistent D1/KV feedback storage, 50–100-case model benchmarking dashboard, automatic prompt-version analytics, and long-term learning workflow. None is required for first safe automatic matching.
- Interface names and environment variable names are consistent across tasks.
- The five Review Focus failures each have an explicit owning test.
