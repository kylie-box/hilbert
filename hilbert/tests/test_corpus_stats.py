from unittest import TestCase
import hilbert as h

try:
    import numpy as np
    from scipy import sparse
    import torch
except ImportError:
    np = None
    sparse = None
    torch = None


class TestCorpusStats(TestCase):


    def test_PMI(self):
        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
        Nxx, Nx, Nxt, N = bigram.load_shard()
        expected_PMI = torch.log(Nxx*N / (Nx * Nxt))
        found_PMI = h.corpus_stats.calc_PMI(bigram)
        self.assertTrue(torch.allclose(found_PMI, expected_PMI, atol=1e-5))


#    def test_sparse_PMI(self):
#        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
#        Nxx, Nx, Nxt, N = bigram.load_shard()
#        expected_PMI = torch.log(Nxx*N / (Nx * Nxt))
#        expected_PMI[expected_PMI==-np.inf] = 0
#        pmi_data, I, J = h.corpus_stats.calc_PMI_sparse(bigram)
#        self.assertTrue(len(pmi_data) < np.product(bigram.Nxx.shape))
#        found_PMI = sparse.coo_matrix((pmi_data,(I,J)),bigram.Nxx.shape)
#        self.assertTrue(np.allclose(found_PMI.toarray(), expected_PMI))


    def test_PMI_star(self):
        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
        Nxx, Nx, Nxt, N = bigram.load_shard()
        Nxx = Nxx.clone()
        Nxx[Nxx==0] = 1
        expected_PMI_star = torch.log(Nxx * N / (Nx * Nxt))
        found_PMI_star = h.corpus_stats.calc_PMI_star(bigram)
        self.assertTrue(torch.allclose(
            found_PMI_star, expected_PMI_star, atol=1e-5))


    #def test_get_stats(self):
    #    # Next, test with a cooccurrence window of +/-2
    #    dtype=h.CONSTANTS.DEFAULT_DTYPE
    #    device=h.CONSTANTS.MATRIX_DEVICE
    #    bigram = h.corpus_stats.get_test_bigram(2)

    #    # Sort to make comparison easier
    #    bigram.sort()

    #    Nxx, Nx, Nxt, N = bigram
    #    self.assertTrue(torch.allclose(
    #        Nxx,
    #        torch.tensor(self.N_XX_2, dtype=dtype, device=device)
    #    ))

    #    # Next, test with a cooccurrence window of +/-3
    #    bigram = h.corpus_stats.get_test_bigram(3)
    #    Nxx, Nx, Nxt, N = bigram
    #    self.assertTrue(np.allclose(
    #        Nxx,
    #        torch.tensor(
    #            self.N_XX_3, dtype=dtype, device=device)
    #    ))


    def test_calc_exp_pmi_stats(self):
        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
        Nxx, Nx, Nxt, N = bigram.load_shard()

        PMI = h.corpus_stats.calc_PMI((Nxx, Nx, Nxt, N))
        PMI = PMI[Nxx>0]
        exp_PMI = torch.exp(PMI)
        expected_mean, expected_std = torch.mean(exp_PMI), torch.std(exp_PMI)

        found_mean, found_std = h.corpus_stats.calc_exp_pmi_stats(bigram)

        self.assertTrue(torch.allclose(found_mean, expected_mean))
        self.assertTrue(torch.allclose(found_std, expected_std))


    def test_calc_prior_beta_params(self):

        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
        exp_mean, exp_std = h.corpus_stats.calc_exp_pmi_stats(bigram)
        Nxx, Nx, Nxt, N = bigram.load_shard()
        Pxx_independent = (Nx / N) * (Nxt / N)

        means = exp_mean * Pxx_independent
        stds = exp_std * Pxx_independent
        expected_alpha = means * (means * (1-means) / stds**2 - 1)
        expected_beta = (1-means) / means * expected_alpha

        found_alpha, found_beta = h.corpus_stats.calc_prior_beta_params(
            (Nxx, Nx, Nxt, N), exp_mean, exp_std, Pxx_independent)

        self.assertTrue(torch.allclose(found_alpha, expected_alpha))
        self.assertTrue(torch.allclose(found_beta, expected_beta))


    def test_keep_prob(self):
        t = 1e-5
        bigram, unigram, Nxx = h.corpus_stats.get_test_bigram_base()
        uNx, uNxt, uN = bigram.load_unigram_shard()
        freq = uNx / uN
        p_keep_expected = t / freq + torch.sqrt(t / freq)
        p_keep_expected = torch.clamp(p_keep_expected, 0, 1)
        p_keep_found = h.corpus_stats.w2v_prob_keep(uNx, uN, t)
        self.assertTrue(torch.allclose(p_keep_found, p_keep_expected))



