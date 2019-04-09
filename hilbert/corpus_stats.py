import os
import time
import scipy
import hilbert as h
import matplotlib.mlab as mlab
import matplotlib.pyplot as plt


PMI_MEAN = -0.812392711
PMI_STD = 1.2475529909

try:
    import torch
    import numpy as np
    from scipy import sparse
except ImportError:
    torch = None
    np = None
    sparse = None


####
#
# CONVENIENCE LOADERS FOR GETTING AHOLD OF CORPUS-RELATED TEST DATA STRUCTURES.
#
####

def load_test_tokens():
    return load_tokens(h.CONSTANTS.TEST_TOKEN_PATH)


def load_tokens(path):
    with open(path) as f:
        return f.read().split()


def get_test_stats(window_size):
    return get_stats(load_test_tokens(), window_size, verbose=False)


def get_test_cooccurrence_mutable(window_size):
    cooccurrence = get_cooccurrence_mutable(load_test_tokens(), window_size, verbose=False) 
    return cooccurrence


#def get_test_cooccurrence(window_size):
#    cooccurrence = get_cooccurrence(load_test_tokens(), window_size, verbose=False) 
#    #cooccurrence.sort()
#    return cooccurrence


def get_test_cooccurrence(device=None, verbose=True):
    """
    For testing purposes, builds a cooccurrence from constituents (not using
    it's own load function) and returns the cooccurrence along with the
    constituents used to make it.
    """
    path = os.path.join(h.CONSTANTS.TEST_DIR, 'cooccurrence')
    unigram = h.unigram.Unigram.load(path, device=device, verbose=verbose)
    Nxx = sparse.load_npz(os.path.join(path, 'Nxx.npz')).tolil()
    cooccurrence = h.cooccurrence.Cooccurrence(
        unigram, Nxx, device=device, verbose=verbose)

    return cooccurrence, unigram, Nxx


def get_test_cooccurrence_sector(sector):
    """
    For testing purposes, builds a `CooccurrenceSector` starting from a `Cooccurrence`
    (not using `Cooccurrence`'s load function) and returns both.
    """
    cooccurrence = h.cooccurrence.Cooccurrence.load(
        os.path.join(h.CONSTANTS.TEST_DIR, 'cooccurrence'))
    args = {
        'unigram':cooccurrence.unigram,
        'Nxx':cooccurrence.Nxx[sector],
        'Nx':cooccurrence.Nx,
        'Nxt':cooccurrence.Nxt,
        'sector':sector
    }
    cooccurrence_sector = h.cooccurrence_sector.CooccurrenceSector(**args)
    return cooccurrence_sector, cooccurrence



#############
#
# Operations on Corpus Statistics used by models.
#
#############

def w2v_prob_keep(uNx, uN, t=1e-5):
    freqs = uNx / uN
    drop_probs = torch.clamp((freqs - t)/freqs - torch.sqrt(t/freqs), 0, 1)
    keep_probs = 1 - drop_probs
    return keep_probs


def calc_PMI(cooccurrence_shard):
    Nxx, Nx, Nxt, N = cooccurrence_shard
    return torch.log(N) + torch.log(Nxx) - torch.log(Nx) - torch.log(Nxt)


def calc_prior_beta_params(cooccurrence, exp_mean, exp_std, Pxx_independent):
    _, Nx, Nxt, N = cooccurrence
    mean = exp_mean * Pxx_independent
    std = exp_std * Pxx_independent
    alpha = mean * (mean*(1-mean)/std**2 - 1)
    beta = (1-mean) * alpha / mean 
    return alpha, beta


def calc_exp_pmi_stats(cooccurrence):
    Nxx, _, _, _ = cooccurrence
    pmi = h.corpus_stats.calc_PMI(cooccurrence)
    # Keep only pmis for i,j where Nxx[i,j]>0
    pmi = pmi[Nxx>0]
    exp_pmi = np.e**pmi
    return torch.mean(exp_pmi), torch.std(exp_pmi)



#############
#
#    Stuff below here is scratch used for real-time analysis, but not
#    necessarily good outside use.  Keeping it for now.
#
#############

def posterior_pmi_histogram(
    post_alpha, post_beta, factor, a=-20, b=5, delta=0.01
):
    X = np.arange(a,b,delta)
    pdf = [
        (factor * np.e**x)**(post_alpha-1) * (1-factor*np.e**x)**(post_beta-1)
        for x in X
    ]
    Y = pdf / np.sum(pdf)
    plt.plot(X,Y)
    plt.show()


def get_posterior_numerically(
    Nij, Ni, Nj, N, pmi_mean=PMI_MEAN, pmi_std=PMI_STD, 
    a=-10, b=10, delta=0.1,
    plot=True
):
    X = np.arange(a, b, delta)
    pmi_pdf = np.array([
        scipy.stats.norm.pdf(x, pmi_mean, pmi_std)
        for x in X
    ])

    pmi_pdf = pmi_pdf / np.sum(pmi_pdf)
    factor = Ni * Nj / N**2
    p = [factor * np.e**x for x in X]

    bin_pdf = np.array([
        scipy.stats.binom.pmf(Nij, N, p_)
        for p_ in p
    ])

    post_pdf = bin_pdf * pmi_pdf
    post_pdf = post_pdf / np.sum(post_pdf)

    if plot:
        plt.plot(X, pmi_pdf, label='prior')
        plt.plot(X, post_pdf, label='posterior')
        plt.legend()
        plt.show()

    return X, post_pdf, pmi_pdf


def calculate_all_kls(cooccurrence):
    assert cooccurrence.sector == h.shards.whole, "expecting whole cooccurrence"
    KL = np.zeros((cooccurrence.vocab, cooccurrence.vocab))
    iters = 0
    start = time.time()
    for i in range(cooccurrence.vocab):
        elapsed = time.time() - start
        start = time.time()
        print(elapsed)
        print(elapsed * 20000 / 60, 'min')
        print(elapsed * 20000 / 60 / 60, 'hrs')
        print(elapsed * 20000 / 60 / 60 / 24, 'days')
        print(100 * iters / 10000**2, '%')
        print('iters', iters)
        for j in range(cooccurrence.vocab):
            iters += 1

            Nij = cooccurrence.Nxx[i,j]
            Ni = cooccurrence.Nx[i,0]
            Nj = cooccurrence.Nx[j,0]
            N = cooccurrence.N
            KL[i,j] = get_posterior_kl(
                MEAN_PMI, PMI_STD, Nij, Ni, Nj, N
            )

    
def get_posterior_kl(
    pmi_mean, pmi_std, Nij, Ni, Nj, N,
    a=-10, b=10, delta=0.1, plot=False
):
    X, posterior, prior = get_posterior_numerically(
        pmi_mean, pmi_std, Nij, Ni, Nj, N, a=a, b=b, delta=delta, plot=plot)
    return kl(posterior, prior)


def kl(pdf1, pdf2):
    # strip out cases where pdf1 is zero
    pdf2 = pdf2[pdf1!=0]
    pdf1 = pdf1[pdf1!=0]

    return np.sum(pdf1 * np.log(pdf1 / pdf2))


def plot_beta(alpha, beta):
    X = np.arange(0, 1, 0.01)
    Y = scipy.stats.beta.pdf(X, alpha, beta)
    plt.plot(X, Y)
    plt.show()


def histogram(values, plot=True):
    values = values.reshape(-1)

    n, bins = np.histogram(values, bins='auto')
    bin_centers = [ 0.5*(bins[i]+bins[i+1]) for i in range(len(n))]

    if plot:
        plt.plot(bin_centers, n)
        plt.show()
    return bin_centers, n


def calc_PMI_smooth(cooccurrence):
    Nxx, Nx, Nxt, N = cooccurrence


    Nxx_exp = Nx * Nxt / N

    Nxx_smooth = torch.tensor([
        [
            Nxx[i,j] if Nxx[i,j] > Nxx_exp[i,j] else
            Nxx_exp[i,j] if Nxx_exp[i,j] > 1 else
            1
            for j in range(Nxx.shape[1])
        ]
        for i in range(Nxx.shape[0])
    ])
    Nx = Nxx_smooth.sum(dim=1, keepdim=True)
    Nxt = Nxx_smooth.sum(dim=0, keepdim=True)
    N = Nxx_smooth.sum()
    return Nxx_smooth, Nx, Nxt, N



def calc_PMI_star(cooc_stats):
    Nxx, Nx, Nxt, N = cooc_stats
    useNxx = Nxx.clone()
    useNxx[useNxx==0] = 1
    return calc_PMI((useNxx, Nx, Nxt, N))



# There should be some code that generates a CooccurrenceMutable by sampling text
# It should exhibit the different samplers too.  For now this stub is a
# reminder.
def get_cooccurrence_mutable(token_list, window_size, verbose=True):
    unigram = h.unigram.Unigram(verbose=verbose)
    for token in token_list:
        unigram.add(token)
    cooccurrence = h.cooccurrence_mutable.CooccurrenceMutable(unigram, verbose=verbose)
    for i in range(len(token_list)):
        focal_word = token_list[i]
        for j in range(i-window_size, i +window_size+1):
            if i==j or j < 0:
                continue
            try:
                context_word = token_list[j]
            except IndexError:
                continue
            cooccurrence.add(focal_word, context_word)
    return cooccurrence




def get_cooccurrence(token_list, window_size, verbose=True):
    unigram = h.unigram.Unigram(verbose=verbose)
    for token in token_list:
        unigram.add(token)
    cooccurrence = h.cooccurrence.Cooccurrence(unigram, verbose=verbose)
    for i in range(len(token_list)):
        focal_word = token_list[i]
        for j in range(i-window_size, i +window_size+1):
            if i==j or j < 0:
                continue
            try:
                context_word = token_list[j]
            except IndexError:
                continue
            cooccurrence.add(focal_word, context_word)
    return cooccurrence






#def calc_PMI_sparse(cooccurrence):
#    I, J = cooccurrence.Nxx.nonzero()
#    log_Nxx_nonzero = np.log(np.array(cooccurrence.Nxx.tocsr()[I,J]).reshape(-1))
#    log_Nx_nonzero = np.log(cooccurrence.Nx[I,0])
#    log_Nxt_nonzero = np.log(cooccurrence.Nxt[0,J])
#    log_N = np.log(cooccurrence.N)
#    pmi_data = log_N + log_Nxx_nonzero - log_Nx_nonzero - log_Nxt_nonzero
#
#    # Here, the default (unrepresented value) in our sparse representation
#    # is negative infinity.  scipy sparse matrices only support zero as the
#    # unrepresented value, and this would be ambiguous with actual zeros.
#    # Therefore, keep data in the (data, (I,J)) format (the same as is used
#    # as input to the coo_matrix constructor).
#    return pmi_data, I, J

