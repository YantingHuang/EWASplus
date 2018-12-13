##running script: match all features to all WGBS sites. Called as python WGBS_all_sites_feature_preprocess.py -a True

import os
import sys
from common import commons
home = commons.home
extra_storage = commons.extra_storage
from features_preprocess import BED_binning
from features_preprocess import BED_Preprocess, CADD_Preprocess,DANN_Preprocess,Eigen_Preprocess,GenoCanyon_Preprocess
import subprocess
import pandas as pd
from features_preprocess import get_winid
import numpy as np
import re
from features_preprocess import WGBS_preprocess
from common.commons import rename_features
import gc
import argparse

def wgbs_sites_selection(tss,allsites):
    tss = tss.sort_values(['chr','coordinate'])
    allsites = all_sites.sort_values(['chr','coordinate'])
    i = 0
    selected_sites = []
    #selected_sites = pd.DataFrame(columns=['chr','coordinate','tss_coordinate'])
    tss['before'] = tss['coordinate']-100000
    tss['after'] = tss['coordinate']+100000
    for row in allsites.iterrows():
        if i >= len(tss):
            break
        chr = row[1]['chr']
        coordinate = row[1]['coordinate']
        winid = row[1]['winid']
        if chr==tss.ix[i,'chr'] and coordinate>=tss.ix[i,'before'] and coordinate<=tss.ix[i,'after']:
            selected_sites.extend([[winid,chr,coordinate,tss.ix[i,'chr'],tss.ix[i,'coordinate']]])
        else:
            while  i<len(tss) and (chr>tss.ix[i,'chr'] or (chr==tss.ix[i,'chr'] and coordinate>tss.ix[i,'after'])):
                i += 1
            if i<len(tss) and chr==tss.ix[i,'chr'] and coordinate>=tss.ix[i,'before'] and coordinate<=tss.ix[i,'after']:
                selected_sites.extend([[winid,chr,coordinate,tss.ix[i,'chr'],tss.ix[i,'coordinate']]])
    df = pd.DataFrame(selected_sites,columns=['winid','chr','coordinate','tss_chr','tss_coordinate'])
    df['chr'] = df['chr'].astype('i8')
    return df


def nearest_tss(tss,sites_df):
    merged = pd.merge(sites_df,tss,how='outer',on=['chr','coordinate'])
    merged.sort_values(['chr','coordinate'],inplace=True)
    merged.rename(columns={'strand':'before_tss'},inplace=True)
    merged.ix[merged['before_tss'].isnull()==False, 'before_tss'] = merged.ix[merged['before_tss'].isnull()==False,'coordinate']
    merged['after_tss'] = merged['before_tss']
    merged['before_tss'].fillna(method='ffill', inplace=True)
    merged['after_tss'].fillna(method='bfill',inplace=True)
    merged['dist_to_before_tss'] = np.abs(merged['coordinate']-merged['before_tss'])
    merged['dist_to_after_tss'] = np.abs(merged['coordinate']-merged['after_tss'])
    merged['tss'] = None
    before_ix = (merged['dist_to_before_tss'] < merged['dist_to_after_tss']) | (merged['dist_to_after_tss'].isnull())
    merged.ix[before_ix,'tss'] = merged.ix[before_ix,'before_tss']
    after_ix = (merged['dist_to_before_tss'] >= merged['dist_to_after_tss']) | (merged['dist_to_before_tss'].isnull())
    merged.ix[after_ix,'tss'] = merged.ix[after_ix,'after_tss']
    merged['dist_to_nearest_tss'] = np.abs(merged['coordinate']-merged['tss'])
    merged.drop(['before_tss','after_tss','tss','dist_to_before_tss','dist_to_after_tss'],axis=1,inplace=True)
    merged.dropna(axis=0,inplace=True)
    return merged


parser = argparse.ArgumentParser(description='Adding all features to all WGBS sites')
parser.add_argument('-a',required=False,default=True,help='feature set',dest='all',metavar='All WGBS sites?')
args = parser.parse_args()

dataset = 'WGBS'
all_wgbs_sites_file = home+'data/'+dataset+'/all_wgbs_sites_winid.csv'
all_sites = pd.read_csv(all_wgbs_sites_file)

chrs = all_sites['chr'].unique()
cols=['chr', 'coordinate','strand']
tss =  pd.read_csv(home+'data/commons/tss.txt',sep='\s+',header=None,names=cols,skiprows=1)
tss = get_winid.convert_chr_to_num(tss,chrs)

all_wgbs_sites = args.all
if all_wgbs_sites:
    selected_wgbs_tss = all_sites
else:
    selected_wgbs_tss = wgbs_sites_selection(tss,all_sites)
    with pd.HDFStore(home+'data/'+dataset+'/all_selected_wgbs_sites','w') as h5s:
    h5s['all_wgbs'] = selected_wgbs_tss


    
start_pos = 0
end_pos = len(selected_wgbs_tss)-1
ranges = np.arange(start_pos,end_pos,1000000)
ranges = np.append(ranges,end_pos)    

for i in np.arange(len(ranges)-1):
    start = ranges[i]
    end = ranges[i+1]
    print("start processing range %d to %d"%(start,end))
    selected_wgbs = selected_wgbs_tss[start:end]
    sites_file = home+'data/'+dataset+'/all_sites_winid.csv'
    selected_wgbs.to_csv(sites_file,index=False)
    selected_wgbs.to_csv(home+'data/'+dataset+'/selected_pos_winid.csv',columns=['winid'],index=False,header=None)
    additional_feature_file = home+'data/features/'+dataset+'/addtional_features_'+str(start)+'_'+str(end)
    subprocess.call([home+'code/features_preprocess/Feature_export.R',home+'data',dataset,'False'])
    
    gc.collect()
    
    WGBS_h5s = home+'data/commons/WGBS_single_H5S'
    WGBS_proc = WGBS_preprocess.WGBS_Preprocess(h5s_file=WGBS_h5s,data_dir=extra_storage+'WGBS/',sites_file=sites_file,additional_feature_file=additional_feature_file,hg19_file= home+'data/WGBS/hg19_WGBS.csv')
    if not os.path.exists(WGBS_h5s):
        WGBS_proc.process()
    WGBS_proc.scores()
    
    ATAC_h5s = home+'data/commons/ATAC_H5S'
    if os.path.exists(ATAC_h5s):
        atac_process = BED_Preprocess.BED_Preprocessing(h5s_file=ATAC_h5s,sites_file=sites_file,additional_feature_file=additional_feature_file,data_type='ATAC')
        atac_process.process()
    else:
        atac_binning = BED_binning.BED_binning(data_type='ATAC',data_dir=extra_storage+'ATAC/',output=ATAC_h5s,sorted=True)
        atac_binning.binning()
        atac_process = BED_Preprocess.BED_Preprocessing(h5s_file=ATAC_h5s,sites_file=sites_file,additional_feature_file=additional_feature_file,data_type='ATAC')
        atac_process.process() 
        
    
    RNASeq_h5s = home+'data/RNASeq/'
    if len(os.listdir(RNASeq_h5s))>0:
        rnaseq_process = BED_Preprocess.BED_Preprocessing(h5s_file=RNASeq_h5s,sites_file=sites_file,additional_feature_file=additional_feature_file, data_type='RNASeq')
        rnaseq_process.process()
    else:
        subprocess.call(['python',home+'code/feature_preprocess/RNASeq_binning.py'])
        rnaseq_process = BED_Preprocess.BED_Preprocessing(h5s_file=RNASeq_h5s,sites_file=sites_file,additional_feature_file=additional_feature_file, data_type='RNASeq')
        rnaseq_process.process()
        
    cadd_preprocess = CADD_Preprocess.CADD_Preprocess(sites_file=sites_file,additional_feature_file=additional_feature_file)
    cadd_preprocess.process()
    
    dann_preprocess = DANN_Preprocess.DANN_Preprocess(sites_file=sites_file,additional_feature_file=additional_feature_file)
    dann_preprocess.process()
    
    eigen_preprocess = Eigen_Preprocess.Eigen_Preprocess(sites_file=sites_file,additional_feature_file=additional_feature_file)
    eigen_preprocess.process()
    
      
    genocanyon_scores = extra_storage+'GenoCanyon/Results/'+dataset+'/selected_site_scores.txt'
    data_dir=extra_storage+'GenoCanyon/Results/'+dataset+'/'
    if os.path.exists(genocanyon_scores):
        genocanyon_preprocess = GenoCanyon_Preprocess.GenoCanyon_Preprocess(data_dir=data_dir,sites_file=sites_file,additional_feature_file=additional_feature_file)
        genocanyon_preprocess.process('selected_site_scores.txt')
    else:
        print('Running GenoCanyon R script...')
        subprocess.call([home+'code/features_preprocess/GenoCanyon_Preprocess.R',"FALSE",home,extra_storage,dataset])
        
        
    selected_wgbs = pd.read_csv(home+'data/'+dataset+'/all_sites_winid.csv')
    feature_dir = home+'data/features/'+dataset+'/'
    files = os.listdir(feature_dir)
    pattern = '.*all.csv$'
    reg = re.compile(pattern)
    files = [name for name in files if len(reg.findall(name))>0]
    
    for file in files:    
        feature = pd.read_csv(feature_dir+file)
        print(len(feature.columns))
        selected_wgbs = pd.concat([selected_wgbs,feature],axis=1)
    
    rename_features(selected_wgbs)
    additional_features = ['ATAC','CADD','DANN','Eigen','GenoCanyon','RNASeq','WGBS']
    
    #merge with additional features
    with pd.HDFStore(additional_feature_file,'r') as h5s:
        for feature in additional_features:
            feature_frame = h5s[feature]
            selected_wgbs = pd.concat([selected_wgbs,feature_frame],axis=1)
    selected_wgbs = selected_wgbs.loc[:,~selected_wgbs.columns.duplicated()]
    selected_wgbs['chr'] = selected_wgbs['chr'].astype('i8')
    
    #nearest tss distance    
    chrs = selected_wgbs['chr'].unique()
    cols=['chr', 'coordinate','strand']
    tss =  pd.read_csv(home+'data/commons/tss.txt',sep='\s+',header=None,names=cols,skiprows=1)
    tss = get_winid.convert_chr_to_num(tss,chrs)
    tss.sort_values(['chr','coordinate'],inplace=True)
    selected_wgbs = nearest_tss(tss,selected_wgbs)
    with pd.HDFStore(home+'data/'+dataset+'/all_features_'+str(start)+'_'+str(end),'w') as h5s:
        h5s['all_features'] = selected_wgbs
    
    gc.collect()    