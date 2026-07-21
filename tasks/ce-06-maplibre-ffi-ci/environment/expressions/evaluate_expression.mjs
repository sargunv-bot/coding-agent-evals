#!/usr/bin/env node
const root = process.env.CAE_ACTIONS_EXPRESSIONS_ROOT ?? "/opt/gha-expressions/node_modules/@actions/expressions";
const { Evaluator, Lexer, Parser, data } = await import(`${root}/dist/index.js`);
const { truthy } = await import(`${root}/dist/result.js`);

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const request = JSON.parse(Buffer.concat(chunks).toString("utf8"));
const expression = request.expression.trim().replace(/^\$\{\{\s*/, "").replace(/\s*\}\}$/, "");
const lexer = new Lexer(expression);
const { tokens } = lexer.lex();
const parser = new Parser(tokens, ["matrix"], []);
const tree = parser.parse();
const context = JSON.parse(JSON.stringify(request.context), data.reviver);
const result = new Evaluator(tree, context).evaluate();
process.stdout.write(`${JSON.stringify({ enabled: truthy(result) })}\n`);
