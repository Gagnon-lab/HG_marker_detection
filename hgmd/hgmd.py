import pandas as pd
import numpy as np
import xlmhg as hg
import scipy.stats as ss


# TODO: Raise some exceptions!
def get_cell_data(marker_path, tsne_path, cluster_path):
    """Parses cell data into a DataFrame.


    Combines data at given paths into a single DataFrame. Assumes standard csv
    format, with each row corresponding to a single cell, and each column
    either to a single gene, a tSNE score, or a cluster identifier.

    Args:
        marker_path: Path to file containing gene expression data.
        tsne_path: Path to file containing tSNE score data.
        cluster_path: Path to file containing cluster data.

    Returns:
        A single pandas DataFrame incorporating all cell data. Row values are
        cell identifiers. The first column is cluster number. The 2nd and 3rd
        columns are tSNE_1 and tSNE_2 scores. All following columns are gene
        names, in the order given by the file at tsne_path.

    Raises:
        IOError: An error occurred accessing the files at marker_path,
            tsne_path, and cluster_path.
        ValueError: The files at marker_path, tsne_path, and cluster_path have
            inappropriate formatting.
    """

    # TODO: make this not have to fiddle so much with the CSV; the CSV should
    # already be in a nice format
    cell_data = pd.read_csv(marker_path, sep=' ')
    cell_data = cell_data.T
    cluster_data = pd.read_csv(
        cluster_path, engine='python', sep='\s+', header=None, index_col=0
    )
    # TODO: are these assignments necessary?
    cluster_data = cluster_data.rename(index=str, columns={1: "cluster"})
    tsne_data = pd.read_csv(
        tsne_path, engine='python', sep='\s+', header=None, index_col=0
    )
    tsne_data = tsne_data.rename(index=str, columns={1: "tSNE_1", 2: "tSNE_2"})
    cell_data = pd.concat(
        [cluster_data, tsne_data, cell_data], axis=1, sort=True
    )
    return cell_data


def singleton_test(cells, cluster, X, L):
    """Tests and ranks genes and complements using the XL-mHG test and t-test.


    Applies the XL-mHG test and t-test to each gene (and its complement) found
    in the columns of cells using the specified cluster of interest, then
    ranks genes by both mHG p-value and by t-test p-value. Specifically, the
    XL-mHG test calculates the expression cutoff value that best differentiates
    the cluster of interest from the cell population, then calculates the
    cluster's significance value using the hypergeometric and t-test. The final
    rank is the average of these two ranks.  Returns a pandas DataFrame with
    test and rank data by gene.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        cluster: The cluster of interest. Must be in cells['cluster'].values.
        X: A parameter of the XL-mHG test. An integer specifying the minimum
            number of cells in-cluster that should express the gene.
        L: A parameter of the XL-mHG test. An integer specifying the maximum
            number of cells that should express the gene.

    Returns:
        A single pandas DataFrame incorporating test and rank data, sorted
        by combined mHG and t rank. Row values are gene and complement names;
        complements are named by appending '_c' to gene names. Column values
        are:
            'HG_stat': The HG test statistic, measuring significance of the
                cluster at our given expression cutoff.
            'mHG_pval': The significance of our chosen cutoff.
            'mHG_cutoff_index': The expression cutoff index, for a list of all
                cells sorted by expression (descending for normal genes,
                ascending for their complements. Cells at the cutoff index or
                after do not express, while cells before the cutoff index
                express. The index starts at 0.
            'mHG_cutoff_value': Similar to 'mHG_cutoff_index'. The expression
                cutoff value. Cells above the cutoff express, while cells at or
                below the cutoff do not express.
            't_stat': The t-test statistic, measuring significance of the
                cluster at our given expression cutoff.
            't_pval': The p-value corresponding to the t-test statistic.
            'rank': The average of the gene's 'mHG_pval' rank and 't_pval'
                rank. Lower p-value is higher rank. A rank of 1 ("first") is
                higher than a rank of 2 ("second").

    Raises:
        ValueError: cells is in an incorrect format, cluster is not in
        cells['cluster'].values, X is greater than the cluster size or less
        than 0, or L is less than X or greater than the population size.
    """

    output = pd.DataFrame(columns=[
        'gene', 'HG_stat', 'mHG_pval', 'mHG_cutoff_index', 'mHG_cutoff_value',
        't_stat', 't_pval'
    ])
    for index, gene in enumerate(cells.columns[3:]):
        # Do XL-mHG and t-test for selected gene.
        # XL-mHG requires two list inputs, exp and v:
        # exp is a DataFrame with column values: cluster, gene expression.
        # Row values are cells.
        # v is boolean list of cluster membership. Uses 1s and 0s rather than
        # True and False.
        # Both exp and v are sorted by expression (descending).
        print(
            "Testing " + str(gene) + "... [" + str(index + 1) + "/"
            + str(len(cells.columns[3:])) + "]"
        )
        exp = cells[['cluster', gene]]
        exp = exp.sort_values(by=gene, ascending=False)
        v = np.array((exp['cluster'] == cluster).tolist()).astype(int)
        HG_stat, mHG_cutoff_index, mHG_pval = hg.xlmhg_test(v, X=X, L=L)
        mHG_cutoff_value = exp.iloc[mHG_cutoff_index][gene]
        # "Slide up" the cutoff index to where the gene expression actually
        # changes. I.e. for array [5.3 1.2 0 0 0 0], if index == 4, the cutoff
        # value is 0 and thus the index should actually slide to 2.
        # numpy.searchsorted works with ascending, not descending lists.
        # Therefore, negate to make it work.
        mHG_cutoff_index = np.searchsorted(
            -exp[gene].values, -mHG_cutoff_value, side='left'
        )
        # TODO: reassigning sample and population every time is inefficient
        sample = exp[exp['cluster'] == cluster]
        population = exp[exp['cluster'] != cluster]
        t_stat, t_pval = ss.ttest_ind(sample[gene], population[gene])
        gene_data = pd.DataFrame(
            {
                'gene': gene, 'HG_stat': HG_stat, 'mHG_pval': mHG_pval,
                'mHG_cutoff_index': mHG_cutoff_index,
                'mHG_cutoff_value': mHG_cutoff_value,
                't_stat': t_stat, 't_pval': t_pval,
            },
            index=[0]
        )
        output = output.append(gene_data, sort=False, ignore_index=True)

    HG_rank = output['mHG_pval'].rank()
    t_rank = output['t_pval'].rank()
    combined_rank = pd.DataFrame({'rank': HG_rank + t_rank})
    output = output.join(combined_rank)
    output = output.sort_values(by='rank', ascending=True)
    return output


def pair_test(cells, singleton, cluster, min_exp_ratio):
    """Tests and ranks pairs of genes using the hypergeometric test.


    Uses output of singleton_test to apply the hypergeometric test to pairs of
    genes, by finding the significance of the cluster of interest in the set of
    cells expressing both genes. Then, ranks pairs by this significance.
    Designed to use output of singleton_test. Output includes singleton data.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        singleton: A DataFrame with format matching those returned by
            singleton_test.
        cluster: The cluster of interest. Must be in cells['cluster'].values.
        min_exp_ratio: The minimum expression ratio for consideration. Genes
            which are expressed by a fraction of the cluster of interest less
            than this value are ignored. Usually these genes are unhelpful,
            and ignoring them helps with speed.

    Returns:
        A single pandas DataFrame incorporating test data, sorted by HG test
        statistic. Row values are unimportant. Column values are:
            'gene': The first gene in the pair.
            'gene_B': The second gene in the pair.
            'HG_stat': The HG test statistic, measuring significance of the
                cluster in the subset of cells which express both genes.

    Raises:
        ValueError: cells or singleton is in an incorrect format, cluster is
            not in cells['cluster'].values, min_exp_ratio is not in the range
            [0.0,1.0].
    """

    return pd.DataFrame()


def find_TP_TN(cells, singleton, pair, cluster):
    """Finds true positive/true negative rates, appends them to our DataFrames.


    Uses output of singleton_test and pair_test to find true positive and true
    negative rates for gene expression relative to the cluster of interest.
    Appends rates to these output DataFrames.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        singleton: A DataFrame with format matching those returned by
            singleton_test.
        pair: A DataFrame with format matching those returned by pair_test.
        cluster: The cluster of interest. Must be in cells['cluster'].values.

    Returns:
        Nothing; argument DataFrames are edited directly.

    Raises:
        ValueError: cells, singleton, or pair is in an incorrect format, or
            cluster is not in cells['cluster'].values.
    """

    pass


def make_discrete_plots(cells, singleton, pair, plot_pages, path):
    """Creates plots of discrete expression and saves them to pdf.


    Uses output of singleton_test and pair_test to create plots of discrete
    gene expression. For gene pairs, plot each individual gene as well,
    comparing their plots to the pair plot. Plots most significant genes/pairs
    first.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        singleton: A DataFrame with format matching those returned by
            singleton_test.
        pair: A DataFrame with format matching those returned by pair_test.
        plot_pages: The maximum number of pages to plot. Each gene or gene pair
            corresponds to one page.
        path: Save the plot pdf here.

    Returns:
        Nothing.

    Raises:
        ValueError: cells, singleton, or pair is in an incorrect format,
            plot_pages is less than 1.
    """

    pass


def make_combined_plots(
    cells, singleton, pair, plot_pages, pair_path, singleton_path
):
    """Creates a plot of discrete and continuous expression and saves to pdf.


    Uses output of singleton_test and pair_test to create plots of discrete and
    continuous expression. For gene pairs, make these two plots for each gene
    in the pair. Plots most significant genes/pairs first. Also makes a similar
    plot using only singletons.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        singleton: A DataFrame with format matching those returned by
            singleton_test.
        pair: A DataFrame with format matching those returned by pair_test.
        plot_pages: The maximum number of pages to plot. Each gene or gene pair
            corresponds to one page.
        pair_path: Save the full plot pdf here.
        singleton_path: Save the singleton-only plot pdf here.

    Returns:
        Nothing.

    Raises:
        ValueError: cells, singleton, or pair is in an incorrect format,
            plot_pages is less than 1.
    """

    pass


def make_TP_TN_plots(
    cells, singleton, pair, plot_genes, pair_path, singleton_path
):
    """Creates plots of true positive/true negative rates and saves to pdf.


    Uses output of find_TP_TN to create plots of true positive and true
    negative rate by gene or gene pair. Plots most significant genes/pairs
    first. Also makes a similar plot using only singletons.

    Args:
        cells: A DataFrame with format matching those returned by
            get_cell_data. Row values are cell identifiers, columns are first
            cluster identifier, then tSNE_1 and tSNE_2, then gene names.
        singleton: A DataFrame with format matching those returned by
            singleton_test.
        pair: A DataFrame with format matching those returned by pair_test.
        plot_genes: Number of genes/pairs to plot. More is messier!
        pair_path: Save the full plot pdf here.
        singleton_path: Save the singleton-only plot pdf here.

    Returns:
        Nothing.

    Raises:
        ValueError: cells, singleton, or pair is in an incorrect format,
            plot_pages is less than 1.
    """

    pass