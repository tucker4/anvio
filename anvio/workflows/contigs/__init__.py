# -*- coding: utf-8
# pylint: disable=line-too-long
"""
    Classes to define and work with anvi'o contigs workflows.
"""


import anvio
import anvio.terminal as terminal

from anvio.workflows import WorkflowSuperClass


__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2018, the Meren Lab (http://merenlab.org/)"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Alon Shaiber"
__email__ = "alon.shaiber@gmail.com"


run = terminal.Run()
progress = terminal.Progress()

class ContigsDBWorkflow(WorkflowSuperClass):
    def __init__(self, config):
        WorkflowSuperClass.__init__(self, config)

        self.rules.extend(['anvi_script_reformat_fasta', 'remove_human_dna_using_centrifuge',
                           'anvi_gen_contigs_database', 'export_gene_calls', 'centrifuge',
                           'anvi_import_taxonomy', 'anvi_run_hmms', 'anvi_run_ncbi_cogs',
                           'annotate_contigs_database'])

        self.general_params.extend(["references_txt"])

        self.rule_acceptable_params_dict['anvi_run_ncbi_cogs'] = ['run', '--cogs-data-dir', '--sensitive', '--temporary-dir-path', '--search-with']

        self.rule_acceptable_params_dict['anvi_run_hmms'] = ['run', '--installed-hmm-profile', '--hmm-profile-dir']

        self.rule_acceptable_params_dict['centrifuge'] = ['run']

        self.rule_acceptable_params_dict['anvi_script_reformat_fasta'] = \
                    ['run', '--simplify-names', '--keep-ids', '--exclude-ids', '--min-len']

        self.rule_acceptable_params_dict['remove_human_dna_using_centrifuge'] = ['run']

        gen_contigs_params = ['--description', '--skip-gene-calling', '--external-gene-calls',\
                              '--ignore-internal-stop-codons', '--skip-mindful-splitting',\
                              '--contigs-fasta', '--project-name', '--output-db-path',\
                              '--description', '--split-length', '--kmer-size',\
                              '--skip-mindful-splitting', '--skip-gene-calling', '--external-gene-calls',\
                              '--ignore-internal-stop-codons']

        self.rule_acceptable_params_dict['anvi_gen_contigs_database'] = gen_contigs_params


