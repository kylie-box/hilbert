import hilbert as h
import torch
from hilbert.generic_datastructs import Describable


class ModelBatchLoader(Describable):
    """
    Base class for any LoaderModel that implements the common functionality,
    being, iteration over the preloaded shards.
    """

    def __init__(self, cooccurrence_preloader, verbose=True, device=None):
        self.preloader = cooccurrence_preloader
        self.verbose = verbose
        self.device = device

        # these Nones are used in the iterator pattern
        self.preloaded_batches = None
        self.crt_batch_id = None
        self.preload_all_batches() # fill 'er up!


    def __iter__(self):
        self.crt_batch_id = -1
        return self


    def __next__(self):
        self.crt_batch_id += 1

        if self.crt_batch_id >= len(self.preloaded_batches):
            raise StopIteration

        preloaded = self.preloaded_batches[self.crt_batch_id]
        prepared = self.preloader.prepare(preloaded)
        return self._load(prepared)


    def __len__(self):
        return len(self.preloaded_batches)


    def describe(self):
        return self.preloader.describe()


    def preload_all_batches(self):
        self.preloaded_batches = []

        if self.verbose:
            print('Preloading all shards...')

        for preload_data in self.preloader.preload_iter():
            self.preloaded_batches.append(preload_data)

        if self.verbose:
            print('Preloading complete!')


    def _load(self, preloaded):
        raise NotImplementedError('Subclasses must extend `_load`!')



class PPMILoader(ModelBatchLoader):

    def _load(self, preloaded):
        batch_id, cooccurrence_data, unigram_data = preloaded
        cooccurrence_data = tuple(
            tensor.to(self.device) for tensor in cooccurrence_data)
        M = h.corpus_stats.calc_PMI(cooccurrence_data)
        M = torch.clamp(M, min=0)
        return batch_id, {'M': M}

    def describe(self):
        return 'PPMI Sharder\n' + super(PPMILoader, self).describe()



class GloveLoader(ModelBatchLoader):

    def __init__(
            self,
            cooccurrence_preloader,
            X_max=100.0,
            alpha=0.75,
            **kwargs
        ):
        super(GloveLoader, self).__init__(cooccurrence_preloader, **kwargs)
        self.X_max = float(X_max)
        self.alpha = alpha


    def _load(self, preloaded):
        batch_id, cooccurrence_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(
            tensor.to(self.device) for tensor in cooccurrence_data)
        weights = (Nxx / self.X_max).pow(self.alpha)
        weights = torch.clamp(weights, max=1.)
        M = torch.log(Nxx)
        Nxx_is_zero = (Nxx==0)
        M[Nxx_is_zero] = 0
        weights[Nxx_is_zero] = 0
        weights = weights * 2
        return batch_id, {'M': M, 'weights': weights}


    def describe(self):
        s =  'GloVe Sharder\n'
        s += '\tX_max = {}\n'.format(self.X_max)
        s += '\talpha = {}\n'.format(self.alpha)
        s += super(GloveLoader, self).describe()
        return s



class SGNSLoader(ModelBatchLoader):

    def __init__(self, cooccurrence_preloader, k=15, **kwargs):
        super(SGNSLoader, self).__init__(cooccurrence_preloader, **kwargs)
        self.k = torch.tensor(
            k, device=self.device, dtype=h.CONSTANTS.DEFAULT_DTYPE)

    def _load(self, preloaded):
        batch_id, cooccurrence_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(
            tensor.to(self.device) for tensor in cooccurrence_data)
        uNx, uNxt, uN = tuple(tensor.to(self.device) for tensor in unigram_data)
        N_neg = self.negative_sample(Nxx, Nx, uNxt, uN, self.k)
        return batch_id, {'Nxx': Nxx, 'N_neg': N_neg}

    def describe(self):
        s = 'Word2Vec Sharder\n'
        s += '\tk = {}\n'.format(self.k)
        s += super(SGNSLoader, self).describe()
        return s

    @staticmethod
    def negative_sample(Nxx, Nx, uNxt, uN, k):
        return k * (Nx - Nxx) * (uNxt / uN)



class MLELoader(ModelBatchLoader):

    def _load(self, preloaded):
        batch_id, cooccurrence_data, unigram_data = preloaded
        Nxx, Nx, Nxt, N = tuple(
            tensor.to(self.device) for tensor in cooccurrence_data)
        Pxx_data = Nxx / N
        Pxx_independent = (Nx / N) * (Nxt / N)
        return (
            batch_id, 
            {'Pxx_data': Pxx_data, 'Pxx_independent': Pxx_independent}
        )

    def describe(self):
        return 'MLESharder\n' + super(
            MLELoader, self).describe()






