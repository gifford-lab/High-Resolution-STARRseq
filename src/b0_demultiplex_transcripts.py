# 
import _config
from _config import OUT_PLACE,LOGS_PLACE, EXP_DESIGN_2955, EXP_DESIGN_3447
import sys, os, fnmatch, datetime, subprocess, imp,json
import numpy as np
from collections import defaultdict
sys.path.append('/cluster/bh0085/')
from mybio import util
import pandas as pd

import itertools as it
import re


#__file__ = "b_dm_test"

# Default params
inp_dir = OUT_PLACE + 'a_split/'
try: NAME = util.get_fn(__file__)
except NameError: NAME="0627_b0_tests"

logs_dir = os.path.join(LOGS_PLACE, NAME)
util.ensure_dir_exists(logs_dir)
out_dir = os.path.join(OUT_PLACE,NAME+"/")
util.ensure_dir_exists(out_dir)

exp_design_2955=EXP_DESIGN_2955
exp_design_3447=EXP_DESIGN_3447


exp_test_strs_2955 = {}
for k,r in exp_design_2955.iterrows():
    exp_test_strs_2955[r.Name] = "{0}+{1}".format(r["i7 Index reads"].strip(),r["i5 Index reads"].strip())


exp_test_strs_3447 = {}
for k,r in exp_design_3447.iterrows():
    exp_test_strs_3447[r.Name] = "{0}+{1}".format(r["i7 Index reads"].strip(),r["i5 Index reads"].strip())



##
# primary
##
def demultiplex(split, filename):

  if "AH3W5GBGX9" in filename:
      print()
      exp_design = exp_design_2955
      exp_test_strs = exp_test_strs_2955
  else:
      
      exp_design = exp_design_3447
      exp_test_strs = exp_test_strs_3447
      
  for name in list(exp_design["Name"]) + ['other']:
      util.ensure_dir_exists(os.path.join(out_dir, '%s'% (filename), name  ))
      util.exists_empty_fn(os.path.join(out_dir, '%s/%s/R1_%s.fa' % (filename,name,split)))
      util.exists_empty_fn(os.path.join(out_dir, '%s/%s/R2_%s.fa' % (filename,name,split)))

  print(os.path.join(out_dir, name, '%s' % (filename)))
  for snum, sgroup in it.groupby(
        sorted(os.listdir(inp_dir),key=lambda x:re.compile("(\d+)\.fastq").search(x).groups()[0])
    , key=lambda x:re.compile("(\d+)\.fastq").search(x).groups()[0]):

      if snum != split: continue
      files = list(sgroup)
      fns =  list([sf for sf in files if filename in sf])

      print(("LANE: {0}, FILES: {1}".format(snum, fns)))
      read_files =dict([[ int(re.compile("R(\d+)").search(e).group(1)),e] for e in fns])

      inp_fn1 = os.path.join(inp_dir, read_files[1])
      inp_fn2 = os.path.join(inp_dir, read_files[2])

      lc = util.line_count(inp_fn1)
      num_bad_q, num_tot, num_other,num_mapped = 0, 0, 0, 0
      timer = util.Timer(total = lc)
      i = -1

      ##
      # Functions
      ##
      def match(r1,r2, h1,h2):   
        for k, v in list(exp_test_strs.items()):
          try:
              idx = h1.index(v)
              return k,r1
          except ValueError as e:
              continue
        return "other",r1

      with open(inp_fn1) as f1:
        with open(inp_fn2) as f2:
          print(inp_fn1)
          print(inp_fn2)  
          while 1:
            i+=1
            if i % 10000 ==0 : 
              print(("{0} records, ({1}%) [{2} bad] [{3} other]".format(i/4 , 100*float(i) / lc, num_bad_q,num_other)))

            try: 
              line1 = next(f1)
              line2 = next(f2)
            except StopIteration as e:
              break

            if i % 4 == 0:
              h1 = line1.strip()
              h2 = line2.strip()
            if i % 4 == 1:
              r1 = line1.strip()
              r2 = line2.strip()
            if i % 4 == 3:
              num_tot += 1
              qs1 = line1.strip()
              qs2 = line2.strip()

              markbad = False
              for qs in [qs1,qs2]:
                  quals = [ord(s)-33 for s in qs]
                  if np.mean(quals) < 30:
                    markbad = True

              if markbad: 
                num_bad_q += 1
                continue

              demultiplex_id, trimmed_read = match(r1,r2, h1,h2)
              if demultiplex_id == 'other':
                num_other += 1

              out1_fn = out_dir +  '%s/%s/R1_%s.fa' % (filename,demultiplex_id, split)
              if len(('>' + h1[1:] + '\n' + r1 + '\n').splitlines()) > 2:
                print('>' + h1[1:] + '\n' + r1 + '\n')
                raise Exception()
              #print('>' + h1[1:] + '\n' + r1 + '\n')
              with open(out1_fn, 'a') as f:
                f.write('>' + h1[1:] + '\n' + r1 + '\n')


              out2_fn = out_dir +  '%s/%s/R2_%s.fa' % (filename,demultiplex_id, split)
              with open(out2_fn, 'a') as f:
                f.write('>' + h2[1:] + '\n' + r2 + '\n')
              num_mapped+=1

            #timer.update()

  #logs = pd.Series({"num_bad_q":num_bad_q,
  #               "num_tot":num_tot})
  #logs.to_csv(os.path.join(LOGS_DIR,f"{datetime.date.today().isoformat}_{filename}_{split}.csv"))
  print(('Rejected %s fraction of reads' % (num_bad_q / num_tot)))
  print("<json>" +json.dumps(
    {"num_bad_q":num_bad_q,
    "num_tot":num_tot,
    "num_other":num_other,
    "num_mapped":num_mapped,
    })+"</json>")


  return



##
# qsub
##
def gen_qsubs():
  # Generate qsub shell scripts and commands for easy parallelization
    print('Generating qsub scripts...')
    qsubs_dir = _config.QSUBS_DIR + NAME + '/'
    util.ensure_dir_exists(qsubs_dir)
    qsub_commands = []

    num_scripts = 0
    runtime = int(datetime.datetime.now().timestamp())
    for fn in os.listdir(inp_dir):
       basename,rnum,snum = re.compile("(.*)_R(\d)_001_(\d+).fastq").search(fn).groups()
       print(basename,rnum, snum)
       print(inp_dir)
       if int(rnum)==1:
         command = '/cluster/bh0085/anaconda27/envs/py3/bin/python %s.py %s %s' % (NAME, snum, basename)
         script_id = NAME.split('_')[0]

         # Write shell scripts
         sh_fn = qsubs_dir + 'q_%s_%s_%s.sh' % (script_id,basename,snum)
         with open(sh_fn, 'w') as f:
           f.write('#!/bin/bash\n%s\n' % (command))
         num_scripts += 1
     
         # Write qsub commands
         outfile = os.path.join(logs_dir,f"o_{runtime}_{basename}_{snum}.txt")
         errorfile = os.path.join(logs_dir,f"e_{runtime}_{basename}_{snum}.txt")

         qsub_commands.append(f'qsub -o {outfile} -e {errorfile} -wd {_config.SRC_DIR} {sh_fn}' )
     
   # Save commands
    with open(qsubs_dir + '_commands.txt', 'w') as f:
     f.write('\n'.join(qsub_commands))

    print('Wrote %s shell scripts to %s' % (num_scripts, qsubs_dir))
    return





##
# Main
##
@util.time_dec
def main(split = '',filename='' ):
  if split == '':
    gen_qsubs()
    return

  demultiplex(split,filename)
  return out_dir


if __name__ == '__main__':
  if len(sys.argv) > 1:
   main(*sys.argv[1:])
  else:
    main()