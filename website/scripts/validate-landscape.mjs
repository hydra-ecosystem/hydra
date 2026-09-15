#!/usr/bin/env node

// Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const landscapeUrl = new URL('../src/data/landscape.json', import.meta.url);
const landscape = JSON.parse(await readFile(landscapeUrl, 'utf8'));

const projectFields = [
  'repository',
  'name',
  'url',
  'description',
  'kind',
  'type',
  'tags',
  'relationships',
  'group',
  'featureCandidate',
  'reviewedAt',
].sort();
const optionalProjectFields = new Set(['homepage']);
const kinds = new Set([
  'application',
  'framework',
  'hydra_developer_tool',
  'learning_resource',
  'library_tool',
  'ml_experimentation_platform',
  'plugin_integration',
  'template_starter',
]);
const relationships = new Set(['extends', 'integrates', 'teaches']);
const groups = new Set(['good_hydra_usage', 'powered_by_hydra']);
const repositories = new Set();
const names = new Set();
const urls = new Set();

assert.deepEqual(Object.keys(landscape).sort(), ['projects', 'schemaVersion']);
assert.equal(landscape.schemaVersion, 2);
assert.ok(Array.isArray(landscape.projects));
assert.ok(landscape.projects.length > 0);

for (const project of landscape.projects) {
  assert.deepEqual(
    Object.keys(project)
      .filter((field) => !optionalProjectFields.has(field))
      .sort(),
    projectFields,
    `${project.repository ?? 'unknown project'} has unexpected fields`,
  );
  assert.match(project.repository, /^[\w.-]+\/[\w.-]+$/);
  assert.ok(!repositories.has(project.repository), `${project.repository} is duplicated`);
  repositories.add(project.repository);
  assert.ok(project.name.trim());
  assert.ok(!names.has(project.name), `${project.name} is duplicated`);
  names.add(project.name);
  assert.ok(project.url.startsWith('https://'));
  assert.ok(!urls.has(project.url), `${project.url} is duplicated`);
  urls.add(project.url);
  if ('homepage' in project) {
    assert.ok(
      project.homepage.startsWith('https://'),
      `${project.repository} has a non-HTTPS homepage`,
    );
    assert.notEqual(
      project.homepage,
      project.url,
      `${project.repository} repeats its repository URL as a homepage`,
    );
  }
  assert.ok(project.description.trim());
  assert.ok(kinds.has(project.kind), `${project.repository} has an invalid kind`);
  assert.ok(project.type.trim(), `${project.repository} has no project type`);
  assert.ok(!project.type.includes(' or '), `${project.repository} has an ambiguous type`);
  assert.ok(project.tags.length > 0);
  assert.deepEqual(project.tags, [...new Set(project.tags)].sort());
  assert.ok(project.tags.every((tag) => /^[a-z][a-z0-9_]*$/.test(tag)));
  assert.deepEqual(
    project.relationships,
    [...new Set(project.relationships)].sort(),
  );
  assert.ok(
    project.relationships.every((relationship) => relationships.has(relationship)),
  );
  assert.ok(groups.has(project.group), `${project.repository} has an invalid group`);
  assert.equal(typeof project.featureCandidate, 'boolean');
  if (project.featureCandidate) {
    assert.equal(project.group, 'good_hydra_usage');
  }
  assert.match(project.reviewedAt, /^\d{4}-\d{2}-\d{2}$/);
}

function compareText(left, right) {
  if (left < right) {
    return -1;
  }
  return left > right ? 1 : 0;
}

const sortedProjects = [...landscape.projects].sort(
  (left, right) =>
    compareText(left.name.toLowerCase(), right.name.toLowerCase()) ||
    compareText(left.repository, right.repository),
);
assert.deepEqual(landscape.projects, sortedProjects, 'projects are not sorted by name');

console.log(`Validated ${landscape.projects.length} Landscape projects.`);
