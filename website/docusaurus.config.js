/**
 * Copyright (c) 2017-present, Facebook, Inc.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

module.exports = {
    title: 'Hydra',
    tagline: 'A framework for elegantly configuring complex applications',
    url: 'https://hydra.cc',
    baseUrl: '/',
    onBrokenLinks: 'throw',
    onBrokenAnchors: 'throw',
    markdown: {
        hooks: {
            onBrokenMarkdownLinks: 'throw',
        },
    },
    trailingSlash: true,
    favicon: 'img/Hydra-head.svg',
    organizationName: 'hydra-ecosystem', // Usually your GitHub org/user name.
    projectName: 'hydra', // Usually your repo name.
    customFields: {
        githubLinkVersionToBaseUrl: {
            "1.4": "https://github.com/hydra-ecosystem/hydra/blob/1.4_branch/",
            "1.3": "https://github.com/hydra-ecosystem/hydra/blob/1.3_branch/",
            "1.2": "https://github.com/hydra-ecosystem/hydra/blob/1.2_branch/",
            "1.1": "https://github.com/hydra-ecosystem/hydra/blob/1.1_branch/",
            "1.0": "https://github.com/hydra-ecosystem/hydra/blob/1.0_branch/",
            current: "https://github.com/hydra-ecosystem/hydra/blob/1.4_branch/",
        },
    },
    themeConfig: {
        algolia: {
            appId: 'KVTVP1D78C',
            apiKey: '9585f41bc128c5a99dd9f22827e1e836',
            indexName: 'hydra',
            algoliaOptions: {},
        },
        announcementBar: {
          id: 'supportus',
          content:
            '⭐️ If you like Hydra, give it a star on <a target="_blank" rel="noopener noreferrer" href="https://github.com/hydra-ecosystem/hydra">GitHub</a>! ⭐️',
        },
		prism: {
		  additionalLanguages: ['antlr4'],
		},
        navbar: {
            title: 'Hydra',
            logo: {
                alt: 'Hydra logo',
                src: 'img/logo.svg',
            },
            items: [
                {to: 'docs/intro', label: 'Docs', position: 'left'},
                {to: 'docs/landscape', label: 'Hydra Landscape', position: 'left'},
                {position: 'left', type: 'docsVersionDropdown'},
                {to: 'blog', label: 'Blog', position: 'left'},
                {to: 'https://github.com/hydra-ecosystem/hydra', label: 'Hydra@GitHub', position: 'left'},
            ],
        },
        footer: {
            style: 'dark',
            links: [
                {
                    label: 'Blog',
                    to: 'blog'
                },
                {
                    label: 'Docs',
                    to: 'docs/intro'
                },
                {
                    label: 'Hydra@GitHub',
                    to: 'https://github.com/hydra-ecosystem/hydra',
                },
                {
                    label: 'Powered by OmegaConf',
                    to: 'https://github.com/omry/omegaconf',
                },
                {
                    label: 'Privacy',
                    to: '/privacy/',
                },
            ],

            copyright: 'Hydra is open source under the MIT License. Copyright remains with the respective copyright holders.',
        },
    },
    presets: [
        [
            '@docusaurus/preset-classic',
            {
                docs: {
                    sidebarPath: require.resolve('./sidebars.js'),
                    showLastUpdateAuthor: false,
                    showLastUpdateTime: false,
                    editUrl: 'https://github.com/hydra-ecosystem/hydra/edit/main/website/',
                    lastVersion: 'current',
                    versions: {
                        current: {
                            label: '1.4 (RC)',
                        },
                    },
                },
                gtag: {
                    trackingID: 'G-1E68PJ51JC',
                },
                theme: {
                    customCss: require.resolve('./src/css/custom.css'),
                },
            },
        ],
    ],
};
