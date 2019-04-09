import os
import numpy as np
import torch
import torch.optim as op
import hilbert as h
from hilbert.cooccurrence import DenseShardPreloader, LilSparsePreloader, TupSparsePreloader


def get_opt(string):
    s = string.lower()
    d = {
        'sgd': op.SGD,
        'adam': op.Adam,
        'adagrad': op.Adagrad,
    }
    return d[s]


def get_init_embs(pth):
    if pth is None:
        return None
    init_embeddings = h.embeddings.Embeddings.load(pth)
    return init_embeddings.V, init_embeddings.W


def build_preloader(
        cooccurrence_path,
        sector_factor=1,
        shard_factor=1,
        t_clean_undersample=None,
        alpha_unigram_smoothing=None,
        datamode='dense',
        is_w2v=False,
        zk=10000,
        n_batches=1000,
        device=None
    ):
    if datamode == 'dense':

        preloader = DenseShardPreloader(
            cooccurrence_path, sector_factor, shard_factor,
            t_clean_undersample=t_clean_undersample,
            alpha_unigram_smoothing=alpha_unigram_smoothing,
        )

    elif datamode == 'tupsparse':
        preloader = TupSparsePreloader(
            cooccurrence_path, zk=zk, n_batches=n_batches,
            t_clean_undersample=t_clean_undersample,
            alpha_unigram_smoothing=alpha_unigram_smoothing,
            filter_repeats=False,
            include_unigram_data=is_w2v,
            device=device,
        )

    elif datamode == 'lilsparse':
        preloader = LilSparsePreloader(
            cooccurrence_path, zk=zk,
            t_clean_undersample=t_clean_undersample,
            alpha_unigram_smoothing=alpha_unigram_smoothing,
            filter_repeats=False,
            include_unigram_data=is_w2v,
            device=device,
        )
    else:
        raise NotImplementedError('datamode {} not implemented'.format(datamode))

    return preloader


### Word2vec ###
def construct_w2v_solver(
        cooccurrence_path,
        init_embeddings_path=None,
        d=300,
        k=15,
        t_clean_undersample=None,
        alpha_unigram_smoothing=0.75,
        update_density=1.,
        learning_rate=0.01,
        opt_str='adam',
        sector_factor=1,
        shard_factor=1,
        seed=1,
        datamode='dense',
        device=None,
        tup_n_batches=None,
        zk=None,
        verbose=True
    ):
    np.random.seed(seed)
    torch.random.manual_seed(seed)

    # make the preloader
    preloader = build_preloader(
        cooccurrence_path,
        sector_factor=sector_factor,
        shard_factor=shard_factor,
        alpha_unigram_smoothing=alpha_unigram_smoothing,
        t_clean_undersample=t_clean_undersample,
        datamode=datamode,
        is_w2v=True,
        n_batches=tup_n_batches,
        zk=zk,
        device=device
    )

    # Make the loader
    loader = h.loaders.Word2vecLoader(
        preloader,
        verbose=verbose,
        device=device,
        k=k,
    )

    # Make the loss.  
    dictionary_path = os.path.join(cooccurrence_path, 'dictionary')
    dictionary = h.dictionary.Dictionary.load(dictionary_path)
    vocab = len(dictionary)
    loss = h.loss.Word2vecLoss(
        keep_prob=update_density, ncomponents=vocab**2, 
    )

    # get initial embeddings (if any)
    init_vecs = get_init_embs(init_embeddings_path)
    shape = None
    if init_vecs is None:
        shape = (vocab, vocab)

    # build the main daddyboy
    embsolver = h.embedder.HilbertEmbedderSolver(
        loader=loader,
        loss=loss,
        optimizer_constructor=get_opt(opt_str),
        d=d,
        learning_rate=learning_rate,
        init_vecs=init_vecs,
        dictionary=dictionary,
        shape=shape,
        one_sided=False,
        learn_bias=False,
        seed=seed,
        verbose=verbose,
        learner=datamode,
        device=device
    )
    if verbose:
        print('finished loading w2v bad boi!')
    return embsolver


### GLOVE ###
def construct_glv_solver(
        cooccurrence_path,
        init_embeddings_path=None,
        d=300,
        alpha=0.75,
        X_max=100,
        t_clean_undersample=None,
        alpha_unigram_smoothing=None,
        update_density=1.,
        learning_rate=0.01,
        opt_str='adam',
        sector_factor=1,
        shard_factor=1,
        seed=1,
        tup_n_batches=None,
        zk=None,
        device=None,
        nobias=False,
        datamode='dense',
        verbose=True
    ):
    if nobias:
        print('NOTE: running GloVe without biases!')

    # repeatability
    np.random.seed(seed)
    torch.random.manual_seed(seed)

    # make the preloader
    preloader = build_preloader(
        cooccurrence_path,
        sector_factor=sector_factor,
        shard_factor=shard_factor,
        alpha_unigram_smoothing=alpha_unigram_smoothing,
        t_clean_undersample=t_clean_undersample,
        datamode=datamode,
        is_w2v=False,
        n_batches=tup_n_batches,
        zk=zk,
        device=device
    )

    # Make cooccurrence loader
    loader = h.loaders.GloveLoader(
        preloader,
        verbose=verbose,
        device=device,
        X_max=X_max,
        alpha=alpha,
    )

    # Make the loss
    dictionary_path = os.path.join(cooccurrence_path, 'dictionary')
    dictionary = h.dictionary.Dictionary.load(dictionary_path)
    vocab = len(dictionary)
    loss = h.loss.MSELoss(
        keep_prob=update_density, ncomponents=vocab**2, 
    )

    # initialize the vectors
    init_vecs = get_init_embs(init_embeddings_path)
    shape = None
    if init_vecs is None:
        shape = (vocab, vocab)

    # get the solver and we good!
    embsolver = h.embedder.HilbertEmbedderSolver(
        loader=loader,
        loss=loss,
        optimizer_constructor=get_opt(opt_str),
        d=d,
        learning_rate=learning_rate,
        init_vecs=init_vecs,
        dictionary=dictionary,
        shape=shape,
        one_sided=False,
        learn_bias=not nobias,
        seed=seed,
        device=device,
        learner=datamode,
        verbose=verbose
    )
    return embsolver


def construct_max_likelihood_sample_based_solver(
    cooccurrence_path,
    init_embeddings_path=None,
    d=300,
    temperature=1,
    #update_density=1.,
    learning_rate=0.01,
    opt_str='adam',
    sector_factor=1,
    #shard_factor=1,
    batch_size=10000,
    batches_per_epoch=1000,
    #tup_n_batches=None,
    seed=1,
    device=None,
    verbose=True
):
    """
    Similar to construct_max_likelihood_solver, but it is based on 
    approximating the loss function using sampling.
    """

    # repeatability
    np.random.seed(seed)
    torch.random.manual_seed(seed)

    # Make cooccurrence loader
    loader = h.cooccurrence.SampleLoader(
        cooccurrence_path=cooccurrence_path, 
        sector_factor=sector_factor,
        temperature=temperature,
        batch_size=batch_size,
        batches_per_epoch=batches_per_epoch,
        device=device, 
        verbose=verbose
    )

    # Make the loss.  This sample based loss is simpler than the others:
    # it doesn't need to know the vocabulary size nor does it make use of
    # update_density.
    loss = h.loss.SampleMaxLikelihoodLoss()

    # initialize the vectors
    init_vecs = get_init_embs(init_embeddings_path)
    shape = None
    dictionary_path = os.path.join(cooccurrence_path, 'dictionary')
    dictionary = h.dictionary.Dictionary.load(dictionary_path)
    if init_vecs is None:
        vocab = len(dictionary)
        shape = (vocab, vocab)

    # get the solver and we good!
    embsolver = h.embedder.HilbertEmbedderSolver(
        loader=loader,
        loss=loss,
        optimizer_constructor=get_opt(opt_str),
        d=d,
        learning_rate=learning_rate,
        init_vecs=init_vecs,
        dictionary=dictionary,
        shape=shape,
        one_sided=False,
        learn_bias=False,
        seed=seed,
        device=device,
        learner='sparse',
        verbose=verbose
    )
    return embsolver



def _construct_tempered_solver(
    loader_class,
    loss_class,
    cooccurrence_path,
    init_embeddings_path=None,
    d=300,
    temperature=1,
    t_clean_undersample=None,
    alpha_unigram_smoothing=None,
    update_density=1.,
    learning_rate=0.01,
    opt_str='adam',
    sector_factor=1,
    shard_factor=1,
    tup_n_batches=None,
    zk=None,
    seed=1,
    device=None,
    datamode='dense',
    verbose=True
):
    np.random.seed(seed)
    torch.random.manual_seed(seed)

    # make the preloader
    preloader = build_preloader(
        cooccurrence_path,
        sector_factor=sector_factor,
        shard_factor=shard_factor,
        alpha_unigram_smoothing=alpha_unigram_smoothing,
        t_clean_undersample=t_clean_undersample,
        datamode=datamode,
        n_batches=tup_n_batches,
        is_w2v=False,
        zk=zk,
        device=device
    )

    # Now make the loader.
    loader = loader_class(
        preloader,
        verbose=verbose,
        device=device,
    )

    # Make the loss
    dictionary_path = os.path.join(cooccurrence_path, 'dictionary')
    dictionary = h.dictionary.Dictionary.load(dictionary_path)
    vocab = len(dictionary)
    loss = loss_class(
        keep_prob=update_density,
        ncomponents=vocab**2,
        temperature=temperature
    )

    # Get initial embeddings.
    init_vecs = get_init_embs(init_embeddings_path)
    shape = None
    if init_vecs is None:
        shape = (vocab, vocab)

    # Build the main daddyboi!
    embsolver = h.embedder.HilbertEmbedderSolver(
        loader=loader,
        loss=loss,
        optimizer_constructor=get_opt(opt_str),
        d=d,
        learning_rate=learning_rate,
        init_vecs=init_vecs,
        dictionary=dictionary,
        shape=shape,
        one_sided=False,
        learn_bias=False,
        seed=seed,
        device=device,
        learner=datamode,
        verbose=verbose
    )
    return embsolver


def construct_max_likelihood_solver(*args, verbose=True, **kwargs):
    """
    This factory accepts the same set of arguments as
    _construct_tempered_solver, except for sharder_class (which should not be
    provided here).
    """
    simple_loss = kwargs.pop('simple_loss', False)
    if simple_loss:
        loss = h.loss.SimpleMaxLikelihoodLoss
        print("USING SIMPLE!")
    else:
        print("Nothing in life is simple...")
        loss = h.loss.MaxLikelihoodLoss

    solver = _construct_tempered_solver(
        h.loaders.MaxLikelihoodLoader, loss,
        *args, verbose=verbose, **kwargs
    )
    if verbose:
        print('finished loading max-likelihood bad boi!')
    return solver


def construct_max_posterior_solver(*args, verbose=True, **kwargs):
    """
    This factory accepts the same set of arguments as
    _construct_tempered_solver, except for sharder_class (which should not be
    provided here).
    """
    solver = _construct_tempered_solver(
        h.loaders.MaxPosteriorLoader, h.loss.MaxPosteriorLoss,
        *args, verbose=verbose, **kwargs
    )
    if verbose:
        print('finished loading max-posterior bad boi!')
    return solver


def construct_KL_solver(*args, verbose=True, **kwargs):
    """
    This factory accepts the same set of arguments as
    _construct_tempered_solver, except for sharder_class (which should not be
    provided here).
    """
    solver = _construct_tempered_solver(
        h.loaders.KLLoader, h.loss.KLLoss,
        *args, verbose=verbose, **kwargs
    )
    if verbose:
        print('finished loading KL bad boi!')
    return solver
