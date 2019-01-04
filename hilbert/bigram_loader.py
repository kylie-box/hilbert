import hilbert as h
from abc import ABC, abstractmethod
from hilbert.loader import Loader, MultiLoader
try:
    import torch
    from torch.multiprocessing import JoinableQueue, Process
except ImportError:
    torch = None
    JoinableQueue, Process = None, None


class BigramLoaderBase():

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders, 
        queue_size=1, device=None, verbose=True
    ):

        """
        Base class for more specific loaders `BigramLoader` yields tensors 
        representing shards of text cooccurrence data.  Each shard has unigram
        and bigram data, for words and word-pairs, along with totals.

        bigram data:
            `Nxx`   number of times ith word seen with jth word.
            `Nx`    marginalized (summed) counts: num pairs containing ith word
            `Nxt`   marginalized (summed) counts: num pairs containing jth word
            `N`     total number of pairs.

            Note: marginalized counts aren't equal to frequency of the word,
            one word occurrence means participating in ~2 x window-size number
            of pairs.

        unigram data `(uNx, uNxt, uN)`
            `uNx`   Number of times word i occurs.
            `uNxt`  Number of times word j occurs.
            `uN`    total number of words

            Note: Due to unigram-smoothing (e.g. in w2v), uNxt may not equal
            uNx.  In w2v, one gets smoothed, the other is left unchanged (both
            are needed).

        Subclasses can override `_load`, to more specifically choose what
        bigram / unigram data to load, and what other preparations to do to
        make the shard ready to be fed to the model.
        """
        #if num_loaders != sector_factor**2:
        #    raise ValueError(
        #        "`num_loaders` must equal `sector_factor**2`, so that each "
        #        "sector can be assigned to one loader."
        #    )
        self.bigram_path = bigram_path
        self.sector_factor = sector_factor
        self.shard_factor = shard_factor
        self.device = device

        super(BigramLoaderBase, self).__init__(
            num_loaders=num_loaders, queue_size=queue_size, verbose=verbose)


#    def _preload_iter(self, loader_id):
#        sector_id = h.shards.Shards(self.sector_factor)[loader_id]
#        bigram_sector = h.bigram.BigramSector.load(
#            self.bigram_path, sector_id)
#        for shard_id in h.shards.Shards(self.shard_factor):
#            bigram_data = bigram_sector.load_relative_shard(
#                shard=shard_id, device='cpu')
#            unigram_data = bigram_sector.load_relative_unigram_shard(
#                shard=shard_id, device='cpu')
#            yield shard_id * sector_id, bigram_data, unigram_data


    def _preload_iter(self, loader_id):
        for i, sector_id in enumerate(h.shards.Shards(self.sector_factor)):
            if i % self.num_loaders != loader_id:
                continue
            bigram_sector = h.bigram.BigramSector.load(
                self.bigram_path, sector_id)
            for shard_id in h.shards.Shards(self.shard_factor):
                bigram_data = bigram_sector.load_relative_shard(
                    shard=shard_id, device='cpu')
                unigram_data = bigram_sector.load_relative_unigram_shard(
                    shard=shard_id, device='cpu')
                yield shard_id * sector_id, bigram_data, unigram_data


    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        bigram_data = tuple(tensor.to(device) for tensor in bigram_data)
        unigram_data = tuple(tensor.to(device) for tensor in unigram_data)
        return shard_id, bigram_data, unigram_data


class BigramLoader(BigramLoaderBase, Loader):
    pass

class BigramMultiLoader(BigramLoaderBase, MultiLoader):
    pass



class PPMILoader(BigramMultiLoader):

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        bigram_data = tuple(tensor.to(device) for tensor in bigram_data)
        M = h.corpus_stats.calc_PMI(bigram_data)
        M = torch.clamp(M, min=0)
        return shard_id, {'M':M}

    def describe(self):
        s = 'PPMI Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s



class GloveLoader(BigramMultiLoader):

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders,
        X_max=100.0, alpha=0.75, queue_size=1, device=None, verbose=True
    ):
        self.X_max = float(X_max)
        self.alpha = alpha
        super(GloveLoader, self).__init__(
            bigram_path, sector_factor, shard_factor, num_loaders, 
            queue_size=queue_size, device=device, verbose=verbose
        )

    def describe(self):
        s = 'GloVe Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\tX_max = {}\n'.format(self.X_max)
        s += '\talpha = {}\n'.format(self.alpha)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(tensor.to(device) for tensor in bigram_data)
        weights = (Nxx / self.X_max).pow(self.alpha)
        weights = torch.clamp(weights, max=1.)
        M = torch.log(Nxx)
        M[Nxx==0] = 0
        weights[Nxx==0] = 0
        weights = weights * 2
        return shard_id, {'M':M, 'weights':weights}





# sharder for W2V
# noinspection PyCallingNonCallable
class Word2vecLoader(BigramMultiLoader):

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders,
        k=15, queue_size=1, device=None, verbose=True
    ):
        super(Word2vecLoader, self).__init__(
            bigram_path, sector_factor, shard_factor, num_loaders, 
            queue_size=queue_size, device=device, verbose=verbose
        )
        dtype = h.CONSTANTS.DEFAULT_DTYPE
        device = device or h.CONSTANTS.MATRIX_DEVICE
        self.k = torch.tensor(k, device=device, dtype=dtype)

    def describe(self):
        s = 'Word2Vec Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\tk = {}\n'.format(self.k)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(tensor.to(device) for tensor in bigram_data)
        uNx, uNxt, uN = tuple(tensor.to(device) for tensor in unigram_data)
        N_neg = self.negative_sample(Nxx, Nx, uNxt, uN, self.k)
        return shard_id, {'Nxx':Nxx, 'N_neg': N_neg}

    @staticmethod
    def negative_sample(Nxx, Nx, uNxt, uN, k):
        return k * (Nx - Nxx) * (uNxt / uN)



class MaxLikelihoodLoader(BigramMultiLoader):

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders, 
        temperature=1, queue_size=1, device=None, verbose=True
    ):
        super(MaxLikelihoodLoader, self).__init__(
            bigram_path, sector_factor, shard_factor, num_loaders, 
            queue_size=queue_size, device=device, verbose=verbose
        )
        self.temperature = temperature

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(tensor.to(device) for tensor in bigram_data)
        Pxx_data = Nxx / N
        Pxx_independent = (Nx / N) * (Nxt / N)
        return shard_id, {
            'Pxx_data':Pxx_data, 'Pxx_independent':Pxx_independent,
            'temperature': self.temperature
        }

    def describe(self):
        s = 'Max Likelihood Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\ttemperature = {}\n'.format(self.temperature)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s



class MaxPosteriorLoader(BigramMultiLoader):

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders, 
        temperature=1, queue_size=1, device=None, verbose=True
    ):
        super(MaxPosteriorLoader, self).__init__(
            bigram_path, sector_factor, shard_factor, num_loaders, 
            queue_size=queue_size, device=device, verbose=verbose
        )
        self.temperature = temperature

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(tensor.to(device) for tensor in bigram_data)
        Pxx_independent = (Nx / N) * (Nxt / N)
        exp_mean, exp_std =  h.corpus_stats.calc_exp_pmi_stats((Nxx,Nx,Nxt,N))
        alpha, beta = h.corpus_stats.calc_prior_beta_params(
            (Nxx, Nx, Nxt, N), exp_mean, exp_std, Pxx_independent)
        N_posterior = N + alpha + beta - 1
        Pxx_posterior = (Nxx + alpha) / N_posterior
        return shard_id, {
            'N':N,
            'N_posterior':N_posterior,
            'Pxx_posterior': Pxx_posterior,
            'Pxx_independent': Pxx_independent, 'temperature': self.temperature
        }

    def describe(self):
        s = 'Max Posterior Probability Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\ttemperature = {}\n'.format(self.temperature)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s


class KLLoader(BigramMultiLoader):

    def __init__(
        self, bigram_path, sector_factor, shard_factor, num_loaders, 
        temperature=1, queue_size=1, device=None, verbose=True
    ):
        super(KLLoader, self).__init__(
            bigram_path, sector_factor, shard_factor, num_loaders, 
            queue_size=queue_size, device=device, verbose=verbose
        )
        self.temperature = temperature

    def _load(self, preloaded):
        device = self.device or h.CONSTANTS.MATRIX_DEVICE
        shard_id, bigram_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(tensor.to(device) for tensor in bigram_data)
        Pxx_independent = (Nx / N) * (Nxt / N)
        exp_mean, exp_std =  h.corpus_stats.calc_exp_pmi_stats((Nxx,Nx,Nxt,N))
        alpha, beta = h.corpus_stats.calc_prior_beta_params(
            (Nxx,Nx,Nxt,N), exp_mean, exp_std, Pxx_independent)
        N_posterior = N + alpha + beta - 1
        a = Nxx + alpha
        b = N - Nxx + beta
        digamma_a = torch.digamma(a) - torch.digamma(a+b)
        digamma_b = torch.digamma(b) - torch.digamma(a+b)
        return shard_id, {
                'digamma_a': digamma_a,
                'digamma_b': digamma_b,
                'N':N,
                'N_posterior':N_posterior,
                'Pxx_independent': Pxx_independent, 
                'temperature': self.temperature
        }

    def describe(self):
        s = 'KL Sharder\n'
        s += '\tupdate_density = {}\n'.format(self.update_density)
        s += '\ttemperature = {}\n'.format(self.temperature)
        s += '\tmask_diagonal = {}\n'.format(self.mask_diagonal)
        return s



