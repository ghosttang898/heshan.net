import test from "node:test";
import assert from "node:assert/strict";
import { matchesYearSearch, parseYearRange } from "./yearSearch.js";

test("single years match ranges inclusively, including interior years", () => {
  for (const year of ["2006", "2007", "2008"]) assert.equal(matchesYearSearch("2006-2008", year), true);
  for (const year of ["2005", "2009"]) assert.equal(matchesYearSearch("2006-2008", year), false);
  assert.equal(matchesYearSearch("2007", "2007"), true);
  assert.equal(matchesYearSearch("2007", "2006"), false);
});

test("range searches match any intersection, containment or shared boundary", () => {
  for (const query of ["2000-2006", "2008-2010", "2007-2009", "2007-2007", "2000-2010"])
    assert.equal(matchesYearSearch("2006-2008", query), true, query);
  for (const query of ["2000-2005", "2009-2010"])
    assert.equal(matchesYearSearch("2006-2008", query), false, query);
  assert.equal(matchesYearSearch("2007", "2006-2008"), true);
});

test("common separators, Chinese suffixes, whitespace and full-width text are supported", () => {
  for (const value of ["2006 - 2008", "2006\u20132008", "2006\u20142008", "2006~2008", "2006/2008",
    "2006\u81f32008", "2006\u52302008", "2006年 至 2008年", "２００６－２００８"])
    assert.equal(matchesYearSearch(value, "2007"), true, value);
  assert.equal(matchesYearSearch("2006-2008", "２００７年"), true);
});

test("reversed endpoints are normalized for records and queries", () => {
  assert.deepEqual(parseYearRange("2008-2006"), { start: 2006, end: 2008 });
  assert.equal(matchesYearSearch("2008-2006", "2007"), true);
  assert.equal(matchesYearSearch("2007", "2008-2006"), true);
});

test("legacy descriptions retain literal matching and blank searches match all", () => {
  assert.equal(matchesYearSearch("约2007年", "2007"), true);
  assert.equal(matchesYearSearch("90年代", "90年代"), true);
  assert.equal(matchesYearSearch("1990年代", "1990"), true);
  assert.equal(matchesYearSearch("2006-2008", "20"), true);
  assert.equal(matchesYearSearch(null, ""), true);
  assert.equal(matchesYearSearch(undefined, "  "), true);
  assert.equal(matchesYearSearch(null, "2007"), false);
});

test("malformed/free text is not interpreted as a numeric range", () => {
  for (const value of [null, "", "0000", "2006-0000", "200", "20070", "2006-", "2006-2008-2010", "约2007年"])
    assert.equal(parseYearRange(value), null, String(value));
  assert.equal(matchesYearSearch("2006-2008", "2007-"), false);
  assert.equal(matchesYearSearch("unknown", "2007"), false);
});
