# -*- coding: utf-8
# pylint: disable=line-too-long
"""
    Classes to define and work with anvi'o pangenomics workflows.
"""


import anvio
import anvio.terminal as terminal

from anvio.workflows import WorkflowSuperClass
from anvio.workflows.contigs import ContigsDBWorkflow


__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2018, the Meren Lab (http://merenlab.org/)"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Alon Shaiber"
__email__ = "alon.shaiber@gmail.com"


run = terminal.Run()
progress = terminal.Progress()


class PangenomicsWorkflow(ContigsDBWorkflow, WorkflowSuperClass):
    def __init__(self, config):
        ContigsDBWorkflow.__init__(self, config)

        self.rules.extend(['gen_external_genome_file',
                           'anvi_gen_genomes_storage',
                           'anvi_pan_genome'])

        self.general_params.extend(["project_name", "samples_txt"])

        pan_params = ["--project-name", "--output-dir", "--genome-names", "--skip-alignments",\
                     "--align-with", "--exclude-partial-gene-calls", "--use-ncbi-blast",\
                     "--minbit", "--mcl-inflation", "--min-occurrence",\
                     "--min-percent-identity", "--sensitive", "--description",\
                     "--overwrite-output-destinations", "--skip-hierarchical-clustering",\
                     "--enforce-hierarchical-clustering", "--distance", "--linkage"]
        self.rule_acceptable_params_dict['anvi_pan_genome'] = pan_params

        storage_params = ["--internal-genomes", "--external-genomes", "--gene-caller"]
        self.rule_acceptable_params_dict['anvi_gen_genomes_storage'] = storage_params
