"""Four-column Figure 11 renderer using the published notebook style."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from utils.fig11_data import ALGORITHMS, LATENCIES, SIZES, validate_grid


def plot_figure11(records, output):
    """Validate the complete 84-point grid and return plot values and axes."""
    rows = validate_grid(records)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Original notebook cell, using its published proportions and internal legends.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'xtick.labelsize':20,'ytick.labelsize':20,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,4,figsize=(24,5))
    colors={'ar_having-doubling':'#4f669f','a2a_pairwise':'#c73934','a2a_bruck':'#ecbc4a'}
    labels={'ar_having-doubling':'AllReduce','a2a_pairwise':'A2A-Pair','a2a_bruck':'A2A-Bruck'}
    ticks=('125\nkB','500\nkB','2\nMB','8\nMB','32\nMB','128\nMB','512\nMB')
    plotted=[];panel_axes=[]
    for ax,delay in zip(axes,LATENCIES):
        for alg in sorted(ALGORITHMS):
            values=sorted((r for r in rows if r['algorithm']==alg and float(r['T_reconf'])==delay),key=lambda r:float(r['message_mib']))
            x=[float(r['message_mib']) for r in values];y=[r['swot_gap_pct'] for r in values]
            line,=ax.plot(x,y,marker='o',linestyle='--',color=colors[alg],label=labels[alg],linewidth=2,markersize=6)
            assert list(line.get_ydata())==y
            plotted.append({'algorithm':alg,'T_reconf_ms':delay,'message_decimal_MB':x,'residual_gap_pct':y})
        ax.set_xscale('log',base=2);ax.set_xticks(SIZES,labels=ticks)
        ax.set_xlabel('Message Size',fontsize=22)
        ax.set_ylabel('Residual Gap to Ideal (%)',fontsize=20)
        ax.grid(True,alpha=.3)
        ax.set_title(f'T_reconf = {delay} ms',fontsize=20,fontweight='bold')
        if delay==.02:
            # The corrected low-delay curves rise before falling. Place the legend
            # in the clear band between their peaks and Pairwise, rather than over them.
            ax.legend(loc='upper left',bbox_to_anchor=(.01,.94),fontsize=22,
                      labelspacing=.15,borderpad=.3,borderaxespad=.15)
        elif delay==.2:
            ax.legend(loc='lower left',fontsize=22,labelspacing=.15,borderpad=.3)
        else:
            ax.legend(loc='best',fontsize=22)
        lo,hi=ax.get_ylim()
        assert all(lo<float(y)<hi for line in ax.lines for y in line.get_ydata())
        panel_axes.append({'T_reconf_ms':delay,'y_limits':[lo,hi],'y_ticks':list(ax.get_yticks())})
    plt.tight_layout()
    fig.canvas.draw()
    for ax in axes:
        legend_box=ax.get_legend().get_window_extent(fig.canvas.get_renderer())
        for line in ax.lines:
            path=line.get_path().transformed(line.get_transform())
            assert not path.intersects_bbox(legend_box,filled=False),ax.get_title()
    bbox=fig.get_tightbbox(fig.canvas.get_renderer())
    outputs=[]
    for ext in ('pdf','png'):
        p=output.with_suffix('.'+ext)
        fig.savefig(p,bbox_inches='tight',dpi=100)
        outputs.append(p)
    plt.close(fig)
    return {'points': len(rows), 'metric': '100*(SWOT CCT-Ideal CCT)/SWOT CCT',
            'plotted_values': plotted, 'panel_axes': panel_axes,
            'original_canvas_inches': [24, 5], 'legends_do_not_cross_curves': True,
            'output_files': [str(p) for p in outputs]}
