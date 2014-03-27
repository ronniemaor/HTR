import pickle
import os
from os.path import dirname, join, isfile
from glob import glob
from itertools import product
import numpy as np
from scipy.io import savemat
from sklearn.datasets.base import Bunch
from fit_score import loo_score
import config as cfg
from project_dirs import cache_dir, fit_results_relative_path
from utils.misc import ensure_dir, init_array
from utils.formats import list_of_strings_to_matlab_cell_array
from utils.parallel import Parallel, batches

def _cache_file(data, fitter):
    return join(cache_dir(), fit_results_relative_path(data,fitter) + '.pkl')

def _read_one_cache_file(filename):
    if not isfile(filename):
        if cfg.verbosity > 0:
            print 'No cache file {}'.format(filename)
        return {}
    try:
        if cfg.verbosity > 0:
            print 'Reading fits from {}'.format(filename)
        with open(filename) as f:
            fits = pickle.load(f)
            if cfg.verbosity > 0:
                print 'Found {} fits in {}'.format(len(fits),filename)
    except:
        print 'Failed to read fits from {}'.format(filename)
        fits = {}
    return fits
    
def _save_fits(fits, filename, k_of_n):
    if k_of_n is not None:
        k,n = k_of_n
        filename = '{}.{}-of-{}'.format(filename,k,n)
    with open(filename,'w') as f:
        pickle.dump(fits,f)

def _read_all_cache_files(basefile, gene_regions, b_consolidate):
    # collect fits from basefile and all shard files
    fits = _read_one_cache_file(basefile)
    partial_files = set(glob(basefile + '*')) - {basefile}
    for filename in partial_files:
        fits.update(_read_one_cache_file(filename))

    # reduce to the set we need (especially if we're working on a shard)
    fits = {gr:v for gr,v in fits.iteritems() if gr in set(gene_regions)}
        
    if b_consolidate:
        _save_fits(fits,basefile,None)
        for filename in partial_files:
            os.remove(filename)

    return fits

def _get_shard(data, k_of_n):
    gene_regions = list(product(data.gene_names,data.region_names))
    if k_of_n is not None:
        k,n = k_of_n
        gene_regions = [gr for i,gr in enumerate(gene_regions) if i%n == k-1] # k is one-based
    return gene_regions
    
def get_all_fits(data, fitter, k_of_n=None):
    filename = _cache_file(data, fitter)
    ensure_dir(dirname(filename))

    gene_regions = _get_shard(data, k_of_n)
    fits = _read_all_cache_files(filename, gene_regions, b_consolidate = (k_of_n is None))

    missing_fits = set(gr for gr in gene_regions if gr not in fits)
    if cfg.verbosity > 0:
        print 'Still need to compute {}/{} fits'.format(len(missing_fits),len(gene_regions))

    # compute the fits that are missing
    gr_batches = batches(missing_fits, cfg.all_fits_batch_size)
    pool = Parallel(_compute_fit_job)
    for i,gr_batch in enumerate(gr_batches):
        if cfg.verbosity > 0:
            print 'Fitting batch {}/{} ({} fits per batch)'.format(i,len(gr_batches),cfg.all_fits_batch_size)
        changes = pool(pool.delay(data,g,r,fitter) for g,r in gr_batch)
        for g2,r2,f in changes:
            fits[(g2,r2)] = f
        _save_fits(fits, filename, k_of_n)
    return compute_scores(data, fits)  

def _compute_fit_job(data, g, r, fitter):
    series = data.get_one_series(g,r)
    f = compute_fit(series,fitter)
    return g,r,f
    
def compute_scores(data,fits):
    for (g,r),fit in fits.iteritems():
        series = data.get_one_series(g,r)
        try:
            if fit.fit_predictions is None:
                fit.fit_score = None
            else:
                fit.fit_score = cfg.score(series.expression, fit.fit_predictions)
        except:
            fit.fit_score = None
        try:
            fit.LOO_score = loo_score(series.expression, fit.LOO_predictions)
        except:
            fit.LOO_score = None
    return fits
   
def compute_fit(series, fitter):
    if cfg.verbosity > 0:
        print 'Computing fit for {}@{} using {}'.format(series.gene_name, series.region_name, fitter)
    x = series.ages
    y = series.expression
    theta,sigma,LOO_predictions = fitter.fit(x,y,loo=True)
    if theta is None:
        print 'WARNING: Optimization failed during overall fit for {}@{} using {}'.format(series.gene_name, series.region_name, fitter)
        fit_predictions = None
    else:
        fit_predictions = fitter.predict(theta,x)
    
    return Bunch(
        fitter = fitter,
        seed = cfg.random_seed,
        theta = theta,
        sigma = sigma,
        fit_predictions = fit_predictions,
        LOO_predictions = LOO_predictions,
    )

def save_as_mat_file(data, fitter, fits, filename):
    print 'Saving mat file to {}'.format(filename)
    shape = fitter.shape

    gene_names = data.gene_names
    gene_idx = {g:i for i,g in enumerate(gene_names)}
    n_genes = len(gene_names)
    region_names = data.region_names
    region_idx = {r:i for i,r in enumerate(region_names)}
    n_regions = len(region_names)
    
    write_theta = shape.can_export_params_to_matlab()
    if write_theta:
        theta = init_array(np.NaN, shape.n_params(), n_genes,n_regions)
    else:
        theta = np.NaN
    
    fit_scores = init_array(np.NaN, n_genes,n_regions)
    LOO_scores = init_array(np.NaN, n_genes,n_regions)
    fit_predictions = init_array(np.NaN, *data.expression.shape)
    LOO_predictions = init_array(np.NaN, *data.expression.shape)
    for (g,r),fit in fits.iteritems():
        ig = gene_idx[g]
        ir = region_idx[r]
        fit_scores[ig,ir] = fit.fit_score
        LOO_scores[ig,ir] = fit.LOO_score
        if write_theta and fit.theta is not None:
            theta[:,ig,ir] = fit.theta
        original_inds = data.get_one_series(g,r).original_inds
        fit_predictions[original_inds,ig,ir] = fit.fit_predictions
        LOO_predictions[original_inds,ig,ir] = fit.LOO_predictions
    
    mdict = {
        'gene_names' : list_of_strings_to_matlab_cell_array(gene_names),
        'region_names' : list_of_strings_to_matlab_cell_array(region_names),
        'theta' : theta,
        'fit_scores' : fit_scores,
        'LOO_scores' : LOO_scores,
        'fit_predictions' : fit_predictions,
        'LOO_predictions': LOO_predictions,
    }
    savemat(filename, mdict, oned_as='column')
    
def convert_format(filename, f_convert):
    """Utility function for converting the format of cached fits.
       See e.g. scripts/convert_fit_format.py
    """
    with open(filename) as f:
        fits = pickle.load(f)        
    print 'Found cache file with {} fits'.format(len(fits))
    
    print 'Converting...'
    new_fits = {k:f_convert(v) for k,v in fits.iteritems()}
    
    print 'Saving converted fits to {}'.format(filename)
    with open(filename,'w') as f:
        pickle.dump(new_fits,f)

