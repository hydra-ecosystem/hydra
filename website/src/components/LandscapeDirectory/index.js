// Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import React, {useEffect, useMemo, useState} from 'react';

import landscape from '@site/src/data/landscape.json';
import {hashString} from '@site/src/utils/landscape';

import styles from './styles.module.css';

const GROUP_LABELS = {
  all: 'All projects',
  featured: 'Featured projects',
  good_hydra_usage: 'Good Hydra usage',
  powered_by_hydra: 'Powered by Hydra',
};

const KIND_FILTER_LABELS = {
  all: 'All project types',
  application: 'Applications',
  framework: 'Frameworks',
  hydra_developer_tool: 'Hydra developer tools',
  learning_resource: 'Learning resources',
  library_tool: 'Libraries and tools',
  ml_experimentation_platform: 'ML experimentation platforms',
  plugin_integration: 'Plugins and integrations',
  template_starter: 'Templates and starters',
};

const RELATIONSHIP_LABELS = {
  extends: 'Extends Hydra',
  integrates: 'Integrates with Hydra',
  teaches: 'Teaches Hydra',
};

const RELATIONSHIP_FILTER_LABELS = {
  all: 'Any',
  ...RELATIONSHIP_LABELS,
};

function formatTag(tag) {
  return tag
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function LandscapeCard({project}) {
  const isGoodUsage = project.group === 'good_hydra_usage';

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <div>
          <h3 className={styles.projectName}>
            <a href={project.url} rel="noopener noreferrer" target="_blank">
              {project.name}
            </a>
          </h3>
          <div className={styles.projectLinks}>
            <a
              className={styles.repository}
              href={`https://github.com/${project.repository}`}
              rel="noopener noreferrer"
              target="_blank">
              {project.repository}
            </a>
            {project.homepage && (
              <a
                className={styles.homepage}
                href={project.homepage}
                rel="noopener noreferrer"
                target="_blank">
                Homepage
              </a>
            )}
          </div>
        </div>
        <span className={isGoodUsage ? styles.goodUsage : styles.poweredBy}>
          {GROUP_LABELS[project.group]}
        </span>
      </div>

      <p className={styles.description}>{project.description}</p>

      <div className={styles.tags} aria-label="Project tags">
        {project.tags.map((tag) => (
          <span className={styles.tag} key={tag}>
            {formatTag(tag)}
          </span>
        ))}
      </div>

      <div className={styles.cardFooter}>
        <span>{project.type}</span>
        {project.relationships.length > 0 && (
          <span>
            {project.relationships.map((item) => RELATIONSHIP_LABELS[item]).join(' · ')}
          </span>
        )}
      </div>
    </article>
  );
}

export default function LandscapeDirectory() {
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState('all');
  const [kind, setKind] = useState('all');
  const [relationship, setRelationship] = useState('all');
  const [tag, setTag] = useState('all');
  const [dailySeed, setDailySeed] = useState(null);

  useEffect(() => {
    setDailySeed(new Date().toISOString().slice(0, 10));
  }, []);

  const tags = useMemo(
    () => [...new Set(landscape.projects.flatMap((project) => project.tags))].sort(),
    [],
  );

  const projects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const matchingProjects = landscape.projects.filter((project) => {
      const matchesCollection =
        group === 'all' ||
        (group === 'featured' ? project.featureCandidate : project.group === group);
      const searchable = [
        project.name,
        project.repository,
        project.description,
        project.type,
        ...project.tags,
        ...project.tags.map(formatTag),
        ...project.relationships,
        ...project.relationships.map((item) => RELATIONSHIP_LABELS[item]),
      ]
        .join(' ')
        .toLowerCase();
      return (
        (!normalizedQuery || searchable.includes(normalizedQuery)) &&
        matchesCollection &&
        (kind === 'all' || project.kind === kind) &&
        (relationship === 'all' || project.relationships.includes(relationship)) &&
        (tag === 'all' || project.tags.includes(tag))
      );
    });

    if (!dailySeed) {
      return matchingProjects;
    }

    return matchingProjects.sort((left, right) => {
      const difference =
        hashString(`${dailySeed}:${left.repository}`) -
        hashString(`${dailySeed}:${right.repository}`);
      return difference || left.repository.localeCompare(right.repository);
    });
  }, [dailySeed, group, kind, query, relationship, tag]);

  const hasFilters =
    query ||
    group !== 'all' ||
    kind !== 'all' ||
    relationship !== 'all' ||
    tag !== 'all';

  function clearFilters() {
    setQuery('');
    setGroup('all');
    setKind('all');
    setRelationship('all');
    setTag('all');
  }

  return (
    <div className={styles.directory}>
      <div className={styles.filters}>
        <label className={styles.searchField}>
          <span>Search</span>
          <input
            type="search"
            value={query}
            placeholder="Project, repository, or topic"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <label>
          <span>Collection</span>
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            {Object.entries(GROUP_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Project type</span>
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            {Object.entries(KIND_FILTER_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Relationship</span>
          <select
            value={relationship}
            onChange={(event) => setRelationship(event.target.value)}>
            {Object.entries(RELATIONSHIP_FILTER_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Tag</span>
          <select value={tag} onChange={(event) => setTag(event.target.value)}>
            <option value="all">All tags</option>
            {tags.map((value) => (
              <option key={value} value={value}>
                {formatTag(value)}
              </option>
            ))}
          </select>
        </label>

        <button type="button" disabled={!hasFilters} onClick={clearFilters}>
          Clear
        </button>
      </div>

      <p className={styles.resultCount} aria-live="polite">
        Showing {projects.length} of {landscape.projects.length} projects
      </p>

      {projects.length ? (
        <div className={styles.grid}>
          {projects.map((project) => (
            <LandscapeCard key={project.repository} project={project} />
          ))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          <h3>No matching projects</h3>
          <p>Try a different search or clear some filters.</p>
          <button type="button" onClick={clearFilters}>
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}
