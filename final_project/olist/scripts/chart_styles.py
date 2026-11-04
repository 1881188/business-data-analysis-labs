"""Drawing styles checked against the supplied Excel reference workbooks.

Input values are unchanged; gradient fill, corner radius and ring layers are
visual styling. Ring angles encode shares; radial layers are decorative.
"""
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Rectangle, Wedge


def gradient_bars(ax, values, width=.38, rounded=False):
    ax.set_xlim(-.65,len(values)-.35)
    ax.set_ylim(0,max(values)*1.26)
    cmap=LinearSegmentedColormap.from_list('column_gradient',
        ['#0054A6','#00D7D7'] if rounded else ['#00B7E5','#006CAC'])
    xmin,xmax=ax.get_xlim();ymin,ymax=ax.get_ylim()
    aspect=(ymax-ymin)/(xmax-xmin)*ax.bbox.width/ax.bbox.height
    patches=[]
    for i,value in enumerate(values):
        patch=FancyBboxPatch((i-width/2,0),width,value,
            boxstyle=f'round,pad=0,rounding_size={width/2}',mutation_aspect=aspect,
            facecolor='none',edgecolor='none') if rounded else Rectangle((i-width/2,0),width,value,facecolor='none',edgecolor='none')
        ax.add_patch(patch)
        ax.imshow(np.linspace(0,1,256).reshape(-1,1),extent=(i-width/2,i+width/2,0,value),
            cmap=cmap,origin='lower',aspect='auto',interpolation='bicubic',zorder=3,
            clip_path=patch,clip_on=True)
        patches.append(patch)
    return patches


def layered_ring(ax,values,colors):
    total=sum(values);start=90.;wedges=[]
    for i,(value,color) in enumerate(zip(values,colors)):
        end=start-360*value/total
        radius=1.18-i*.10
        wedge=Wedge((0,0),radius,end,start,width=radius-.60,facecolor=color,
                    edgecolor='#1B2043',linewidth=.6)
        ax.add_patch(wedge);wedges.append(wedge)
        for layer in np.arange(.70,radius,.10):
            ax.add_patch(Wedge((0,0),layer,end,start,width=.004,facecolor='#1B2043',edgecolor='none',alpha=.35))
        start=end
    ax.set_aspect('equal');ax.set_xlim(-1.28,1.28);ax.set_ylim(-1.28,1.28)
    return wedges


def smooth_monthly(ax,x,y,color,lw=2.3):
    # PCHIP is display interpolation through observed monthly values;
    # every observed point remains marked, with no new monthly observations.
    from scipy.interpolate import PchipInterpolator
    fine=np.linspace(float(x[0]),float(x[-1]),500)
    ax.plot(fine,PchipInterpolator(x,y)(fine),color=color,lw=lw)
    ax.scatter(x,y,s=10,color=color,zorder=4)
