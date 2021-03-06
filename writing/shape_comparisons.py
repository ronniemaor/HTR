import setup
import numpy as np
import scipy.stats
import matplotlib.pyplot as plt
import config as cfg
from load_data import GeneData
from shapes.sigslope import Sigslope
from shapes.poly import Poly
from shapes.spline import Spline
from fitter import Fitter
from all_fits import get_all_fits, iterate_fits
from scalers import LogScaler
from plots import save_figure

fontsize = 30
larger_fontsize = 48

def plot_comparison_scatter(data, shape1, fits1, shape2, fits2):
    pairs = [(f1.LOO_score, f2.LOO_score) for f1,f2 in iterate_fits(fits1,fits2)]
    scores1,scores2 = zip(*pairs)
    
    fig = plt.figure()
    ax = fig.add_axes([0.12,0.12,0.8,0.8])
    ax.scatter(scores1, scores2, alpha=0.3)
    ax.plot([-1, 1], [-1, 1],'k--')
    ax.set_xlim(-1,1)
    ax.set_ylim(-1,1)
    ticks = [-1,1]
    ax.set_yticks(ticks)
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks], fontsize=fontsize)
    ax.set_yticklabels([str(t) for t in ticks], fontsize=fontsize)
    ax.set_xlabel('$R^2$ for {}'.format(shape1), fontsize=larger_fontsize)
    ax.set_ylabel('$R^2$ for {}'.format(shape2), fontsize=larger_fontsize)
    return fig

def plot_comparison_bar(data, shapes, all_fits, threshold_percentile=None):
    nShapes = len(shapes)

    mu = np.empty(nShapes)
    se = np.empty(nShapes)
    for i,fits in enumerate(all_fits):
        scores = np.array([f.LOO_score for f in iterate_fits(fits, R2_threshold=-1)])
        if threshold_percentile is not None:
            threshold_score = np.percentile(scores, 50)
            scores = scores[scores > threshold_score]
        mu[i] = np.mean(scores)
        se[i] = scipy.stats.sem(scores)
        
    # reorder by mean score
    idx = np.argsort(mu)[::-1]
    mu = mu[idx]
    se = se[idx]
    shapes = [shapes[i] for i in idx]

    index = np.arange(nShapes)
    bar_width = 0.8
    fig = plt.figure()
    ax = fig.add_axes([0.12,0.12,0.8,0.8])
    ax.bar(index, mu, yerr=se, width=bar_width, color='b', error_kw = {'ecolor': '0.3', 'linewidth': 2})  
    ax.set_ylabel('Mean $R^2$', fontsize=fontsize)
    ax.set_xticks(index + bar_width/2)
    ax.set_xticklabels([s.display_name() for s in shapes], fontsize=fontsize)
    yticks = [0, 0.1, 0.2, 0.3]
    ax.set_yticks(yticks)
    ax.set_yticklabels(['{:g}'.format(t) for t in yticks], fontsize=fontsize)
    return fig

def plot_comparison_over_R2_score(data, shapes, all_fits, zoom=None, nbins=50):
    if zoom is None:
        zoom = (-1,1)
    fig = plt.figure()
    ax = fig.add_axes([0.12,0.12,0.8,0.8])
    zoom_max = 0
    for shape,fits in zip(shapes,all_fits):
        scores = np.array([f.LOO_score for f in iterate_fits(fits)])
        scores[scores < -0.999] = -0.999
        h,bins = np.histogram(scores,bins=nbins,density=True)
        xpos = (bins[:-1] + bins[1:])/2
        zoom_data = h[(xpos>=zoom[0]) & (xpos<=zoom[1])]
        zoom_max = max(max(zoom_data),zoom_max)
        ax.plot(xpos,h, linewidth=3, label=shape.display_name())        
    ax.set_xlim(*zoom)
    ax.set_ylim(0,zoom_max*1.1)
    ax.legend(loc='best', fontsize=fontsize, frameon=False)
    ax.set_xlabel('test $R^2$ score', fontsize=fontsize)
    ax.set_ylabel("probability density", fontsize=fontsize)
    ax.tick_params(axis='both', labelsize=fontsize)
    return fig

cfg.verbosity = 1
age_scaler = LogScaler()
pathway = '17full'
data = GeneData.load('both').restrict_pathway(pathway).scale_ages(age_scaler)

sigmoid = Sigslope(priors='sigslope80')
spline = Spline()
poly1 = Poly(1,priors='poly1')
poly2 = Poly(2,priors='poly2')
poly3 = Poly(3,priors='poly3')
shapes = [sigmoid, spline, poly1, poly2, poly3]

fitters = [Fitter(shape, sigma_prior='normal' if not shape.has_special_fitting() else None) for shape in shapes]
fits = [get_all_fits(data,fitter,allow_new_computation=False) for fitter in fitters]

fig = plot_comparison_bar(data, shapes, fits)
save_figure(fig,'RP/shape-comparison-bar-{}.png'.format(data.pathway), under_results=True)

#fig = plot_comparison_bar(data, shapes, fits, threshold_percentile=50)
#save_figure(fig,'RP/shape-comparison-bar-{}-top-half.png'.format(data.pathway), under_results=True)

fig = plot_comparison_over_R2_score(data, shapes, fits)
save_figure(fig,'RP/shape-comparison-vs-R2-{}.png'.format(data.pathway), under_results=True)

fig = plot_comparison_over_R2_score(data, shapes, fits, zoom=(0.3,1))
save_figure(fig,'RP/shape-comparison-vs-R2-{}-zoom.png'.format(data.pathway), under_results=True)

for i in xrange(1,len(shapes)):
    fig = plot_comparison_scatter(data,shapes[0],fits[0],shapes[i],fits[i])
    save_figure(fig,'RP/scatter-{}-{}-{}.png'.format(shapes[0],shapes[i],pathway), under_results=True)

plt.close('all')