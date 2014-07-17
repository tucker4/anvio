#!/usr/bin/env python
# -*- coding: utf-8

# Copyright (C) 2014, A. Murat Eren
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.

import os
import sys
import numpy
import pysam
import random
import cPickle
import operator
import subprocess
import PaPi.utils as utils
from PaPi.utils import pretty_print as pp
from PaPi.contig import Contig
from PaPi.contig import Split


class BAMProfiler:
    """Creates an über class for BAM file operations"""
    def __init__(self, args = None):
        if args:
            self.args = args
            self.input_file_path = args.input_file
            self.serialized_profile_path = args.profile
            self.output_directory = args.output_directory
            self.list_contigs_and_exit = args.list_contigs
            self.min_contig_length = args.min_contig_length
            self.min_mean_coverage = args.min_mean_coverage
            self.number_of_threads = 4 
            self.no_trehading = True
            self.desired_contig_length = args.desired_contig_length

            if args.contigs:
                if os.path.exists(args.contigs):
                    self.contig_names_of_interest = set([c.strip() for c in open(args.contigs).readlines() if c.strip() and not c.startswith('#')])
                else:
                    self.contig_names_of_interest = set([c.strip() for c in args.contigs.split(',')]) if args.contigs else None

            else:
                self.contig_names_of_interest = None

        else:
            self.args = args
            self.input_file_path = None 
            self.serialized_profile_path = None 
            self.output_directory = None 
            self.list_contigs_and_exit = None 
            self.min_contig_length = 10000 
            self.min_mean_coverage = 10
            # FIXME: Parameterize these two:
            self.number_of_threads = 4 
            self.no_trehading = False
            self.desired_contig_length = 20000

        self.bam = None
        self.contigs = {}

        self.progress = utils.Progress()
        self.run = utils.Run()


    def _run(self):
        self.check_args()

        if self.input_file_path:
            self.init_profile_from_BAM()
            self.profile()
            self.store_profile()
        else:
            self.init_serialized_profile()

        self.report()

        runinfo_serialized = self.generate_output_destination('RUNINFO.cPickle')
        self.run.info('runinfo', runinfo_serialized)
        self.run.store_info_dict(runinfo_serialized)
        self.run.quit()


    def init_serialized_profile(self):
        self.progress.new('Init')
        self.progress.update('Reading serialized profile')
        self.contigs = cPickle.load(open(self.serialized_profile_path))
        self.progress.end()

        self.run.info('profile_loaded_from', self.serialized_profile_path)

        self.run.info('num_contigs', pp(len(self.contigs)))

        if self.list_contigs_and_exit:
            print "\nContigs in the file:\n"
            for contig in self.contigs:
                print "\t- %s (%s)" % (contig, pp(int(self.contigs[contig].length)))
            print
            sys.exit()

        if self.contig_names_of_interest:
            contigs_to_discard = set()
            for contig in self.contigs:
                if contig not in self.contig_names_of_interest:
                    contigs_to_discard.add(contig)

            if len(contigs_to_discard):
                for contig in contigs_to_discard:
                    self.contigs.pop(contig)
            self.run.info('num_contigs_selected_for_analysis', pp(len(self.contigs)))

        contigs_to_discard = set()
        for contig in self.contigs.values():
            if contig.length < self.min_contig_length:
                contigs_to_discard.add(contig.name)

        if len(contigs_to_discard):
            if len(contigs_to_discard) == len(self.contigs):
                raise utils.ConfigError, "0 contigs larger than %s nts." % pp(self.min_contig_length)
            else:
                for contig in contigs_to_discard:
                    self.contigs.pop(contig)
                self.run.info('contigs_raw_longer_than_M', len(self.contig_names))

        self.progress.new('Init')
        self.progress.update('Initializing the output directory ...')
        self.init_output_directory()
        self.progress.end()
        self.run.info('output_dir', self.output_directory)


    def init_profile_from_BAM(self):
        self.progress.new('Init')
        self.progress.update('Reading BAM File')
        self.bam = pysam.Samfile(self.input_file_path, 'rb')
        self.progress.end()
        self.run.info('input_bam', self.input_file_path)

        self.contig_names = self.bam.references
        self.contig_lenghts = self.bam.lengths

        try:
            self.num_reads_mapped = self.bam.mapped
        except ValueError:
            raise utils.ConfigError, "It seems the BAM file is not indexed. See 'papi-init-bam' script."

        self.progress.new('Init')
        self.progress.update('Initializing the output directory ...')
        self.init_output_directory()
        self.progress.end()

        runinfo = self.generate_output_destination('RUNINFO')
        self.run.init_info_file_obj(runinfo)
        self.run.info('output_dir', self.output_directory)
        self.run.info('total_reads_mapped', pp(int(self.num_reads_mapped)))
        self.run.info('num_contigs', pp(len(self.contig_names)))

        if self.list_contigs_and_exit:
            print "\nContigs in the file:\n"
            for (contig, length) in zip(self.contig_names, self.contig_lenghts):
                print "\t- %s (%s)" % (contig, pp(int(length)))
            print
            sys.exit()

        if self.contig_names_of_interest:
            indexes = [self.contig_names.index(r) for r in self.contig_names_of_interest if r in self.contig_names]
            self.contig_names = [self.contig_names[i] for i in indexes]
            self.contig_lenghts = [self.contig_lenghts[i] for i in indexes]
            self.run.info('num_contigs_selected_for_analysis', pp(len(self.contig_names)))

        contigs_longer_than_M = set()
        for i in range(0, len(self.contig_names)):
            if self.contig_lenghts[i] > self.min_contig_length:
                contigs_longer_than_M.add(i)
        if not len(contigs_longer_than_M):
            raise utils.ConfigError, "0 contigs larger than %s nts." % pp(self.min_contig_length)
        else:
            self.contig_names = [self.contig_names[i] for i in contigs_longer_than_M]
            self.contig_lenghts = [self.contig_lenghts[i] for i in contigs_longer_than_M]
            self.run.info('contigs_raw_longer_than_M', len(self.contig_names))

        # finally, compute contig splits.
        self.contig_splits = [utils.get_chunks(self.contig_lenghts[i], self.desired_contig_length)\
                                                                 for i in range(0, len(self.contig_names))]


    def init_output_directory(self):
        Absolute = lambda x: os.path.join(os.getcwd(), x) if not x.startswith('/') else x

        if not self.output_directory:
            self.output_directory = Absolute(self.input_file_path) + '-PaPi-OUTPUT'
        else:
            self.output_directory = Absolute(self.output_directory)

        if not os.path.exists(self.output_directory):
            try:
                os.makedirs(self.output_directory)
            except:
                self.progress.end()
                raise utils.ConfigError, "Output directory does not exist (attempt to create one failed as well): '%s'" % \
                                                                (self.output_directory)
        if not os.access(self.output_directory, os.W_OK):
            self.progress.end()
            raise utils.ConfigError, "You do not have write permission for the output directory: '%s'" % self.output_directory


    def generate_output_destination(self, postfix, directory = False):
        return_path = os.path.join(self.output_directory, postfix)

        if directory == True:
            if os.path.exists(return_path):
                shutil.rmtree(return_path)
            os.makedirs(return_path)

        return return_path


    def profile(self):
        """Big deal function"""

        # So we start with essential stats. In the section below, we will simply go through each contig (contig),
        # in the BAM file and populate the contigs dictionary for the first time. There are two major sections,
        # one for no_threading option, and the other with multiple threads.
        
        for i in range(0, len(self.contig_names)):
        
            contig_name = self.contig_names[i]
            contig_splits = self.contig_splits[i]

            contig = Contig(contig_name)
            contig.length = self.contig_lenghts[i]


            self.progress.new('Profiling "%s" (%d of %d) (%s nts)' % (contig.name,
                                                                      i + 1,
                                                                      len(self.contig_names),
                                                                      pp(int(contig.length))))

            # populate contig with empty split objects and 
            for j in range(0, len(contig_splits)):
                start, end = contig_splits[j]
                split_order = j + 1
                split = Split(contig.name, split_order, start, end)
                contig.splits.append(split)

            # analyze coverage for each split
            contig.analyze_coverage(self.bam, self.progress)

            # now we can learn about the mean coverage of the contig.
            discarded_contigs_due_to_C = set([])
            contig_mean_cov = contig.get_mean_self_coverage(self.progress)
            if contig_mean_cov < self.min_mean_coverage:
                # discard this contig and continue
                discarded_contigs_due_to_C.add(contig.name)
                self.progress.end()
                continue

            contig.analyze_auxiliary(self.bam, self.progress)

            contig.analyze_composition(self.bam, self.progress)

            contig.analyze_tnf(self.progress)

            self.progress.end()

            # add contig to the dict.
            self.contigs[contig_name] = contig

        if not len(self.contigs):
            raise utils.ConfigError, "0 contigs passed minimum mean coverage parameter (%d)." % self.min_mean_coverage

        if discarded_contigs_due_to_C:
            self.run.info('contigs_after_C', pp(len(self.contigs)))

        if len(self.contigs) < 3:
            raise utils.ConfigError, "Less than 3 contigs left in your analysis. PaPi can't really do much with this :/ Bye."


    def store_profile(self):
        output_file = self.generate_output_destination('PROFILE.cPickle')
        self.progress.new('Storing Profile')
        self.progress.update('Serializing information for %s contigs ...' % pp(len(self.contigs)))
        cPickle.dump(self.contigs, open(output_file, 'w'))
        self.progress.end()
        self.run.info('profile_dict', output_file)


    def report(self):
        # generate a sorted list of contigs based on length
        self.contig_names = [t[1] for t in sorted([(self.contigs[k].length, k)\
                                                for k in self.contigs], reverse = True)]

        self.progress.new('Generating reports')
        self.progress.update('TNF matrix for contigs')
        TNF_matrix_file_path = self.generate_output_destination('TETRANUCLEOTIDE-FREQ-MATRIX.txt')
        output = open(TNF_matrix_file_path, 'w')
        kmers = sorted(self.contigs[self.contigs.keys()[0]].tnf.keys())
        output.write('contigs\t%s\n' % ('\t'.join(kmers)))
        for contig in self.contigs:
            for split in self.contigs[contig].splits:
                output.write('%s\t' % (split.name))
                output.write('%s\n' % '\t'.join([str(self.contigs[contig].tnf[kmer]) for kmer in kmers]))
        output.close()
        self.progress.end()
        self.run.info('tnf_matrix', TNF_matrix_file_path)


        self.progress.new('Generating reports')
        self.progress.update('Generating the tree of contigs')
        newick_tree_file_path = self.generate_output_destination('TNF-NEWICK-TREE.txt')
        env = os.environ.copy()
        subprocess.call(['papi-TNF-matrix-to-newick.R', '-o', newick_tree_file_path, TNF_matrix_file_path], env = env)
        self.progress.end()
        self.run.info('tnf_tree', newick_tree_file_path)


        # metadata
        self.progress.new('Generating reports')
        self.progress.update('Metadata for contigs')
        metadata_fields = [('essential', 'length'), ('essential', 'mean_coverage'), ('essential', 'std_coverage'), 
                           ('composition', 'GC_content')]

        metadata_txt = open(self.generate_output_destination('METADATA.txt'), 'w')

        metadata_fields = ['contigs', 'length', 'mean_coverage', 'std_coverage', 'GC_content', 'parent']
        metadata_txt.write('%s\n' % ('\t'.join(metadata_fields)))

        F = lambda x: '%.4f' % x
        I = lambda x: '%d' % x

        for contig in self.contigs:
            if len(self.contigs[contig].splits) > 1:
                parent = contig
            else:
                parent = ""

            for split in self.contigs[contig].splits:
                fields = [split.name,
                          I(split.length),
                          F(split.coverage.mean),
                          F(split.coverage.std),
                          F(split.composition.GC_content),
                          parent] 
                metadata_txt.write('%s\n' % '\t'.join(fields))

        metadata_txt.close()
        self.progress.end()
        self.run.info('metadata_txt', metadata_txt.name)

        # contigs FASTA
        self.progress.new('Generating reports')
        self.progress.update('Consensus FASTA file for contigs')
        contigs_fasta = open(self.generate_output_destination('CONTIGS-CONSENSUS.fa'), 'w')
        for contig in self.contig_names:
            for split in self.contigs[contig].splits:
                contigs_fasta.write(">%s\n%s\n" % (split.name,
                                                   split.auxiliary.rep_seq))
        contigs_fasta.close()
        self.progress.end()
        self.run.info('contigs_fasta', contigs_fasta.name)


    def check_args(self):
        if (not self.input_file_path) and (not self.serialized_profile_path):
            raise utils.ConfigError, "You must declare either an input file, or a serialized profile."
        if self.input_file_path and self.serialized_profile_path:
            raise utils.ConfigError, "You can't declare both an input file and a serialized profile."
        if self.serialized_profile_path and (not self.output_directory):
            raise utils.ConfigError, "When loading serialized profiles, you need to declare an output directory."
        if self.input_file_path and not os.path.exists(self.input_file_path):
            raise utils.ConfigError, "No such file: '%s'" % self.input_file_path
        if self.serialized_profile_path and not os.path.exists(self.serialized_profile_path):
            raise utils.ConfigError, "No such file: '%s'" % self.serialized_profile_path
        if not self.min_mean_coverage >= 0:
            raise utils.ConfigError, "Minimum mean coverage must be 0 or larger."
        if not self.min_contig_length >= 0:
            raise utils.ConfigError, "Minimum contig length must be 0 or larger (although using anything\
                                      below 5,000 is kinda silly, UNLESS you are working with mappings of\
                                      multiple samples to a single assembly)."
