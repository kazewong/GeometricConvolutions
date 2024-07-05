import numpy as np
import pylab as plt
import matplotlib.cm as cm
from matplotlib.collections import PatchCollection
from matplotlib.patches import Wedge
import cmastro

# Visualize the filters.

FIGSIZE = (4, 3)
XOFF, YOFF = 0.15, -0.1
TINY = 1.e-5

def setup_plot(figsize=(8,6)):
    return plt.figure(figsize=figsize).gca()

def nobox(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis("off")

def finish_plot(ax, title, xs, ys, D):
    ax.set_title(title)
    if D == 2:
        ax.set_xlim(np.min(xs)-0.55, np.max(xs)+0.55)
        ax.set_ylim(np.min(ys)-0.55, np.max(ys)+0.55)
    if D == 3:
        ax.set_xlim(np.min(xs)-0.75, np.max(xs)+0.75)
        ax.set_ylim(np.min(ys)-0.75, np.max(ys)+0.75)
    ax.set_aspect("equal")
    nobox(ax)

def plot_boxes(ax, xs, ys):
    ax.plot(
        xs[None] + np.array([-0.5, -0.5, 0.5, 0.5, -0.5]).reshape((5,1)),
        ys[None] + np.array([-0.5, 0.5, 0.5, -0.5, -0.5]).reshape((5,1)),
        "k-", 
        lw=0.5, 
        zorder=10,
    )

def fill_boxes(ax, xs, ys, ws, vmin, vmax, cmap, zorder=-100, colorbar=False, alpha=1.):
    plotted_img = ax.imshow(
        ws.reshape((np.max(xs)+1,np.max(ys)+1)).T, 
        vmin=vmin, 
        vmax=vmax, 
        cmap=cmap, 
        alpha=alpha, 
        zorder=-100,
    )
    if colorbar:
        plt.colorbar(plotted_img, ax=ax)

def plot_scalars(ax, spatial_dims, xs, ys, ws, boxes=True, fill=True, symbols=True,
                 vmin=-2., vmax=2., cmap="cma:unph", colorbar=False):
    if boxes:
        plot_boxes(ax, xs, ys)
    if fill:
        fill_boxes(ax, xs, ys, ws, vmin, vmax, cmap, colorbar=colorbar)
    if symbols:
        height = ax.get_window_extent().height
        ss = (5 * height / spatial_dims[0]) * np.abs(ws)
        ax.scatter(xs[ws > TINY], ys[ws > TINY], marker="+", c="k", s=ss[ws > TINY], zorder=100)
        ax.scatter(xs[ws < -TINY], ys[ws < -TINY], marker="_", c="k", s=ss[ws < -TINY], zorder=100)

def plot_vectors(ax, xs, ys, ws, boxes=True, fill=True, vmin=0., vmax=2., cmap="cma:lacerta_r", scaling=0.33):
    if boxes:
        plot_boxes(ax, xs, ys)
    if fill:
        fill_boxes(ax, xs, ys, np.linalg.norm(ws, axis=-1), vmin, vmax, cmap, alpha=0.25)

    normws = np.linalg.norm(ws, axis=1)

    xs = xs[normws > TINY]
    ys = ys[normws > TINY]
    ws = ws[normws > TINY]

    for x, y, w, normw in zip(xs, ys, ws, normws[normws > TINY]):
        ax.arrow(
            x - scaling * w[0],
            y - scaling * w[1], 
            2 * scaling * w[0], 
            2 * scaling * w[1], 
            length_includes_head=True,
            head_width=0.24 * scaling * normw,
            head_length=0.72 * scaling * normw,
            color="k", 
            zorder=100,
        )

def plot_one_tensor(ax, x, y, T, zorder=0, scaling=0.33):
    if np.abs(T[0,0]) > TINY:
        # plot a double-headed arrow
        ax.arrow(
            x - scaling,
            y,
            2 * scaling * np.abs(T[0,0]),
            0,
            length_includes_head=True,
            head_width= 0.24 * scaling,
            head_length=0.72 * scaling,
            color='g' if T[0,0] > TINY else 'k',
            zorder=zorder,
        )
        ax.arrow(
            x + scaling,
            y,
            -2 * scaling * np.abs(T[0,0]),
            0,
            length_includes_head=True,
            head_width= 0.24 * scaling,
            head_length=0.72 * scaling,
            color='g' if T[0,0] > TINY else 'k',
            zorder=zorder,
        )
    if np.abs(T[1,1]) > TINY:
        # plot a double-headed arrow
        ax.arrow(
            x,
            y - scaling,
            0,
            2 * scaling * np.abs(T[1,1]),
            length_includes_head=True,
            head_width= 0.24 * scaling,
            head_length=0.72 * scaling,
            color='g' if T[1,1] > TINY else 'k',
            zorder=zorder,
        )
        ax.arrow(
            x,
            y + scaling,
            0,
            -2 * scaling * np.abs(T[1,1]),
            length_includes_head=True,
            head_width= 0.24 * scaling,
            head_length=0.72 * scaling,
            color='g' if T[1,1] > TINY else 'k',
            zorder=zorder,
        )

    patches = []
    # plot the petals
    if T[0,1] > TINY:
        patches.append(Wedge(
            (x-0.25,y-0.25),
            0.25 * np.abs(T[0,1]),
            45,
            225,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
        patches.append(Wedge(
            (x+0.25,y+0.25),
            0.25 * np.abs(T[0,1]),
            -135,
            45,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
    if T[0,1] < -TINY:
        patches.append(Wedge(
            (x-0.25,y+0.25),
            0.25 * np.abs(T[0,1]),
            135,
            315,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
        patches.append(Wedge(
            (x+0.25,y-0.25),
            0.25 * np.abs(T[0,1]),
            -45,
            135,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
    if T[1,0] > TINY:
        patches.append(Wedge(
            (x-0.25,y-0.25),
            0.25 * np.abs(T[1,0]),
            -135,
            45,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
        patches.append(Wedge(
            (x+0.25,y+0.25),
            0.25 * np.abs(T[1,0]),
            45,
            225,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
    if T[1,0] < -TINY:
        patches.append(Wedge(
            (x-0.25,y+0.25),
            0.25 * np.abs(T[1,0]),
            -45,
            135,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))
        patches.append(Wedge(
            (x+0.25,y-0.25),
            0.25 * np.abs(T[1,0]),
            135,
            315,
            color='b',
            zorder=zorder,
            alpha=0.25,
        ))

    p = PatchCollection(patches, alpha=0.4)
    ax.add_collection(p)

def plot_tensors(ax, xs, ys, ws, boxes=True, vmin=0., vmax=2., cmap="cma:hesperia_r"):
    if boxes:
        plot_boxes(ax, xs, ys)
    for x, y, w in zip(xs, ys, ws):
        normw = np.linalg.norm(w)
        if normw > TINY:
            plot_one_tensor(ax, x, y, w, zorder=100)

def plot_nothing(ax):
    ax.set_title(" ")
    nobox(ax)
    return

def plot_grid(images, names, n_cols, **kwargs):
    n_rows = max(1, np.ceil(len(images) / n_cols).astype(int))
    assert len(images) <= n_cols * n_rows
    bar = 8. # figure width in inches?
    fig, axes = plt.subplots(n_rows, n_cols, figsize = (bar, 1.15 * bar * n_rows / n_cols), # magic
                             squeeze=False)
    axes = axes.flatten()
    plt.subplots_adjust(left=0.001/n_cols, right=1-0.001/n_cols, wspace=0.2/n_cols,
                        bottom=0.001/n_rows, top=1-0.001/n_rows-0.1/n_rows, hspace=0.2/n_rows)
    
    for img, name, axis in zip(images, names, axes):
        img.plot(ax=axis, title=name, **kwargs)
        
    for axis in axes[len(images):]:
        plot_nothing(axis)

    return fig
