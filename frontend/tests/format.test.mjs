import assert from "node:assert/strict";
import test from "node:test";
import { confidence, odds, probability, signedPercent } from "../src/format.ts";

test("probabilities use one decimal", () => {
  assert.equal(probability(0.6142), "61.4 %");
  assert.equal(probability(0.7), "70.0 %");
  assert.equal(probability(null), "—");
});

test("odds use two decimals", () => {
  assert.equal(odds(1.8), "1.80");
  assert.equal(odds(null), "—");
});

test("edge and confidence", () => {
  assert.equal(signedPercent(0.073), "+7.3 %");
  assert.equal(signedPercent(-0.02), "-2.0 %");
  assert.equal(confidence(78.432), "78 / 100");
  assert.equal(confidence(null), "—");
});
