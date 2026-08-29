// Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

module.exports = {
    docs: {
        About: [
            'intro',
            'landscape',
            'version_archive',
        ],
        Tutorials: [
            'tutorials/intro',
            {
                type: 'category',
                label: 'Basic Tutorial',
                items: [
                    {
                        type: 'category',
                        label: 'Your first Hydra app',
                        items: [
                            'tutorials/basic/your_first_app/simple_cli',
                            'tutorials/basic/your_first_app/config_file',
                            'tutorials/basic/your_first_app/using_config',
                            'tutorials/basic/your_first_app/config_groups',
                            'tutorials/basic/your_first_app/defaults',
                            'tutorials/basic/your_first_app/composition',
                        ]
                    },
                    {
                        type: 'category',
                        label: 'Running your Hydra app',
                        items: [
                            'tutorials/basic/running_your_app/multi-run',
                            'tutorials/basic/running_your_app/working_directory',
                            'tutorials/basic/running_your_app/logging',
                            'tutorials/basic/running_your_app/debugging',
                            'tutorials/basic/running_your_app/tab_completion',
                        ]
                    },

                ],
            },

            {
                type: 'category',
                label: 'Structured Configs Tutorial',
                items: [
                    'tutorials/structured_config/intro',
                    'tutorials/structured_config/config_store',
                    'tutorials/structured_config/minimal_example',
                    'tutorials/structured_config/hierarchical_static_config',
                    'tutorials/structured_config/config_groups',
                    'tutorials/structured_config/defaults',
                    'tutorials/structured_config/schema',
                ],
            },
        ],

        'Common Patterns': [
            'patterns/extending_configs',
            'patterns/configuring_experiments',
            'patterns/configuring_plugins',
            'patterns/select_multiple_configs_from_config_group',
            'patterns/specializing_config',
            'patterns/write_protect_config_node',
        ],

        'Configuring Hydra': [
            'configure_hydra/intro',
            'configure_hydra/job',
            'configure_hydra/logging',
            'configure_hydra/workdir',
            'configure_hydra/app_help',
        ],

        'Available Plugins': [
            'plugins/colorlog',
            {
                'Launchers': [
                    'plugins/joblib_launcher',
                    'plugins/ray_launcher',
                    'plugins/rq_launcher',
                    'plugins/submitit_launcher',
                ]
            },
            {
                'Sweepers': [
                    'plugins/ax_sweeper',
                    'plugins/nevergrad_sweeper',
                    'plugins/optuna_sweeper',
                ]
            },
        ],

        'Reference manual': [
            'advanced/terminology',
            'advanced/hydra-command-line-flags',
            {
                type: 'category',
                label: 'Override grammar',
                items: [
                    'advanced/override_grammar/basic',
                    'advanced/override_grammar/extended',
                ]
            },
            'advanced/defaults_list',
            'advanced/overriding_packages',
            {
                type: 'category',
                label: 'Execution whitelist',
                items: [
                    'advanced/execution_whitelist',
                    'advanced/execution_whitelist/scopes',
                    'advanced/execution_whitelist/target_rules',
                    'advanced/execution_whitelist/restricted_targets',
                ]
            },
            {
                type: 'category',
                label: 'Instantiating Objects',
                items: [
                    'advanced/instantiate_objects/overview',
                    'advanced/instantiate_objects/config_files',
                    'advanced/instantiate_objects/structured_config',
                ]
            },
            'advanced/compose_api',
            'advanced/search_path',
            {
                type: 'category',
                label: 'Plugins',
                items: [
                    'advanced/plugins/overview',
                    'advanced/plugins/develop',
                ]
            },
            'advanced/app_packaging',
            'advanced/decorating_main',
            'advanced/jupyter_notebooks',
            'advanced/unit_testing',
        ],

        "Experimental": [
            "experimental/intro",
            "experimental/callbacks",
            "experimental/rerun",
        ],

        'Developer Guide': [
            'development/overview',
            'development/testing',
            'development/style_guide',
            'development/documentation',
            'development/release',
        ],

        'Upgrade Guide': [
            'upgrades/intro',
            {
                type: 'category',
                label: '1.3 to 1.4',
                items: [
                    'upgrades/1.3_to_1.4/prepare_for_1_4',
                    'upgrades/1.3_to_1.4/breaking_changes',
                    'upgrades/1.3_to_1.4/hydra_job_override_dirname',
                    'upgrades/1.3_to_1.4/instantiate_resolution',
                    'upgrades/1.3_to_1.4/execution_whitelist',
                    'upgrades/1.3_to_1.4/nevergrad_sweeper',
                    'upgrades/1.3_to_1.4/slash_in_default',
                ],
            },
            {
                type: 'category',
                label: '1.1 to 1.2',
                items: [
                    'upgrades/1.1_to_1.2/changes_to_hydra_main_config_path',
                    'upgrades/1.1_to_1.2/changes_to_job_working_dir',
                    'upgrades/1.1_to_1.2/changes_to_sweeper_config',
                ],
            },
            {
                type: 'category',
                label: '1.0 to 1.1',
                items: [
                    'upgrades/1.0_to_1.1/changes_to_hydra_main_config_path',
                    'upgrades/1.0_to_1.1/default_composition_order',
                    'upgrades/1.0_to_1.1/defaults_list_override',
                    'upgrades/1.0_to_1.1/defaults_list_interpolation',
                    'upgrades/1.0_to_1.1/changes_to_package_header',
                    'upgrades/1.0_to_1.1/automatic_schema_matching',
                ],
            },
            {
                type: 'category',
                label: '0.11 to 1.0',
                items: [
                    'upgrades/0.11_to_1.0/config_path_changes',
                    'upgrades/0.11_to_1.0/adding_a_package_directive',
                    'upgrades/0.11_to_1.0/strict_mode_flag_deprecated',
                    'upgrades/0.11_to_1.0/object_instantiation_changes',
                ],
            },

        ],
    }
}
