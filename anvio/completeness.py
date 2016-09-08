# -*- coding: utf-8
# pylint: disable=line-too-long

"""
    Classes to compute completeness estimates based on the information stored in search tables in the
    contigs database.
"""

import numpy
from collections import Counter

import anvio
import anvio.tables as t
import anvio.dbops as dbops
import anvio.utils as utils
import anvio.terminal as terminal

from anvio.errors import ConfigError


__author__ = "A. Murat Eren"
__copyright__ = "Copyright 2015, The anvio Project"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "A. Murat Eren"
__email__ = "a.murat.eren@gmail.com"
__status__ = "Development"


run = terminal.Run()
progress = terminal.Progress()


class Completeness:
    def __init__(self, contigs_db_path, source_requested=None, run=run, progress=progress):
        self.run = run
        self.progress = progress

        # hi db
        contigs_db = dbops.ContigsDatabase(contigs_db_path)

        # read info table to get what is available in the db
        info_table = contigs_db.db.get_table_as_dict(t.hmm_hits_info_table_name)

        # identify and remove non-single-copy sources of hmm search results:
        non_singlecopy_sources = set([k for k in info_table.keys() if info_table[k]['search_type'] != 'singlecopy'])
        singlecopy_sources = set([k for k in info_table.keys() if info_table[k]['search_type'] == 'singlecopy'])
        for non_singlecopy_source in non_singlecopy_sources:
            info_table.pop(non_singlecopy_source)

        # get the hmm hits table
        self.hmm_hits_table = contigs_db.db.get_table_as_dict(t.hmm_hits_table_name)

        # read search table (which holds hmmscan hits for splits).
        self.hmm_hits_splits_table = utils.get_filtered_dict(contigs_db.db.get_table_as_dict(t.hmm_hits_splits_table_name), 'source', singlecopy_sources)

        # an example entry in self.hmm_hits_splits_table looks loke this:
        #
        # {
        #    'percentage_in_split'   : 69.6763202725724,
        #    'source'                : u'Campbell_et_al',
        #    'split'                 : u'ANTARCTICAAQUATIC_SMPL_SITE231_3.0UMcontig18439_split_00001',
        #    'hmm_hit_entry_id'      : 1
        # }
        #

        # a little convenience for potential clients:
        self.http_refs = {}
        for source_in_db in info_table:
            self.http_refs[source_in_db] = [h for h in info_table[source_in_db]['ref'].split() if h.startswith('http')][0]

        self.genes_in_db = dict([(s, info_table[s]['genes'].split(', ')) for s in info_table])

        # we're done with the db
        contigs_db.disconnect()

        self.sources = info_table.keys()
        self.domains = set([info_table[source]['domain'] for source in self.sources])
        self.source_to_domain = dict([(source, info_table[source]['domain']) for source in self.sources])
        self.domain_to_sources = [(domain, [source for source in self.sources if info_table[source]['domain'] == domain]) for domain in self.domains]

        if source_requested:
            if source_requested not in self.sources:
                raise ConfigError, 'Requested source "%s" is not one of the single-copy gene sources found in the database.' % source_requested

            # filter out sources that are not requested
            self.sources = [source_requested]
            self.genes_in_db = {source_requested: self.genes_in_db[source_requested]}
            self.hmm_hits_splits_table = utils.get_filtered_dict(self.hmm_hits_splits_table, 'source', set([source_requested]))

        self.unique_gene_id_to_gene_name = {}
        self.splits_unique_gene_id_occurs = {}
        # these will be very useful later. trust me.
        for entry in self.hmm_hits_splits_table.values():
            hmm_hit = self.hmm_hits_table[entry['hmm_hit_entry_id']]
            gene_unique_identifier = hmm_hit['gene_unique_identifier']

            if gene_unique_identifier not in self.unique_gene_id_to_gene_name:
                self.unique_gene_id_to_gene_name[gene_unique_identifier] = hmm_hit['gene_name']

            if gene_unique_identifier not in self.splits_unique_gene_id_occurs:
                self.splits_unique_gene_id_occurs[gene_unique_identifier] = [entry['split']]
            else:
                self.splits_unique_gene_id_occurs[gene_unique_identifier].append(entry['split'])


    def list_hmm_sources(self):
        self.run.warning('', 'HMM SOURCES FOUND', lc='yellow')
        for source in self.sources:
            self.run.info_single(source)


    def get_best_matching_domain(self, d):
        """Returns the domain that gives the highest (completion - redundancy) estimate.

           The input dict is the output of 'get_info_for_splits' (the prameter `d`)
        """

        domain_specific_estimates = []

        for domain in self.domains:
            percent_completion = numpy.mean([d[s]['percent_complete'] for s in d if d[s]['domain'] == domain])
            percent_redundancy = numpy.mean([d[s]['percent_redundancy'] for s in d if d[s]['domain'] == domain])

            domain_specific_estimates.append((percent_completion - percent_redundancy, domain), )

        domain_specific_estimates.sort(reverse=True)

        return domain_specific_estimates[0][1]


    def get_info_for_splits(self, split_names, min_e_value=1e-5, domain_aware=True):
        hmm_hits_splits_table = utils.get_filtered_dict(self.hmm_hits_splits_table, 'split', split_names)

        # we need to restructure 'hits' into a dictionary that gives access to sources and genes in a more direct manner
        info_dict, gene_name_to_unique_id = {}, {}
        for source in self.sources:
            info_dict[source], gene_name_to_unique_id[source] = {}, {}

        # here we go through every hit and populate 'info_dict' and 'gene_name_to_unique_id':
        for entry in hmm_hits_splits_table.values():
            hmm_hit = self.hmm_hits_table[entry['hmm_hit_entry_id']]

            if hmm_hit['e_value'] > min_e_value:
                continue

            source = hmm_hit['source']
            e_value = hmm_hit['e_value']
            gene_name = hmm_hit['gene_name']
            percentage = entry['percentage_in_split']
            gene_unique_id = hmm_hit['gene_unique_identifier']

            if gene_unique_id in info_dict[source]:
                info_dict[source][gene_unique_id]['percentage'] += percentage
            else:
                info_dict[source][gene_unique_id] = {}
                info_dict[source][gene_unique_id] = {'gene_name': gene_name, 'percentage': percentage, 'e_value': e_value}

            if gene_name in gene_name_to_unique_id[source]:
                gene_name_to_unique_id[source][gene_name].add(gene_unique_id)
            else:
                gene_name_to_unique_id[source][gene_name] = set([gene_unique_id])

        # here we generate the results information
        results_dict = {}
        for source in self.sources:
            results_dict[source] = {'domain': self.source_to_domain[source]}

        for source in self.sources:
            genes_count = Counter([v['gene_name'] for v in info_dict[source].values()])

            # report results
            results_dict[source]['percent_complete'] = len(genes_count) * 100.0 / len(self.genes_in_db[source])

            # report redundancy:
            genes_that_occur_multiple_times = [g for g in genes_count if genes_count[g] > 1]
            results_dict[source]['percent_redundancy'] = sum([genes_count[g] - 1 for g in genes_that_occur_multiple_times]) * 100.0 / len(self.genes_in_db[source])

            # identify splits that contribute the same single_copy_gene
            redundants = {}
            for gene_name in genes_that_occur_multiple_times:
                redundants[gene_name] = [self.splits_unique_gene_id_occurs[unique_gene_id] for unique_gene_id in gene_name_to_unique_id[source][gene_name]]
            results_dict[source]['redundants'] = redundants

        return results_dict
