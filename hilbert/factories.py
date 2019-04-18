import os
import numpy as np
import torch
import hilbert as h



def get_optimizer(opt_str, parameters, learning_rate):
    optimizers = {
        'sgd': torch.optim.SGD,
        'adam': torch.optim.Adam,
        'adagrad': torch.optim.Adagrad,
    }
    if opt_str not in optimizers:
        valid_opt_strs = ["{}".format(k) for k in optimizers.keys()]
        valid_opt_strs[-1] = "or " + valid_opt_strs[-1]
        raise ValueError("Optimizer choice be one of '{}'. Got '{}'.".format(
            ', '.join(valid_opt_strs), opt_str
        ))
    return optimizers[opt_str](parameters, lr=learning_rate)



def get_init_embs(path, device):
    if path is None:
        return None
    device = h.utils.get_device(device)
    inits = h.embeddings.Embeddings.load(path)
    return [
        None if p is None else p.to(device)
        for p in (inits.V, inits.W, inits.vb, inits.wb)
    ]



def build_mle_sample_solver(
        cooccurrence_path
        save_embeddings_dir,
        simple_loss=False,   # MLE option
        temperature=2,       # MLE option
        batch_size=10000,    # Dense option
        bias=False,
        init_embeddings_path=None,
        dimensions=300,
        learning_rate=0.01,
        opt_str='adam',
        num_writes=100,
        num_updates=100000,
        seed=1917,
        device=None,
        verbose=True,
    ):
    """
    Similar to build_mle_solver, but it is based on 
    approximating the loss function using sampling.
    """

    np.random.seed(seed)
    torch.random.manual_seed(seed)

    dictionary = h.dictionary.Dictionary.load(
        os.path.join(cooccurrence_path, 'dictionary'))

    loss = h.loss.SampleMLELoss()

    learner = h.learner.SampleLearner(
        vocab=len(dictionary),
        covocab=len(dictionary),
        d=d,
        bias=bias,
        init=get_init_embs(init_embeddings_path, device),
        device=device
    )

    loader = h.cooccurrence.SampleLoader(
        cooccurrence_path=cooccurrence_path, 
        temperature=temperature,
        batch_size=batch_size,
        device=device, 
        verbose=verbose
    )

    optimizer = get_optimizer(opt_str, learner.parameters(), learning_rate)

    solver = h.solver.Solver(
        loader=loader,
        loss=loss,
        learner=learner,
        optimizer=optimizer,
        schedulers=[],
        dictionary=dictionary,
        verbose=verbose,
    )
    return solver



def build_mle_solver(
        cooccurrence_path
        save_embeddings_dir,
        simple_loss=False,  # MLE option
        temperature=2,      # MLE option
        shard_factor=1,     # Dense option
        bias=False,
        init_embeddings_path=None,
        dimensions=300,
        learning_rate=0.01,
        opt_str='adam',
        num_writes=100,
        num_updates=100000,
        #batch_size,
        seed=1917,
        device=None,
        verbose=True,
    ):

    np.random.seed(seed)
    torch.random.manual_seed(seed)

    dictionary = h.dictionary.Dictionary.load(
        os.path.join(cooccurrence_path, 'dictionary'))

    if simple_loss:
        loss = h.loss.SimpleMLELoss(ncomponents=len(dictionary)**2)
    else:
        loss = h.loss.MLELoss(ncomponents=len(dictionary)**2)

    learner = h.learner.DenseLearner(
        vocab=len(dictionary),
        covocab=len(dictionary),
        d=d,
        bias=bias,
        init=get_init_embs(init_embeddings_path, device),
        device=device
    )

    loader = h.loader.DenseLoader(
        cooccurrence_path,
        shard_factor,
        include_unigrams=loss.INCLUDE_UNIGRAMS,
        device=device
        verbose=verbose,
    )

    optimizer = get_optimizer(opt_str, learner.parameters(), learning_rate)

    solver = h.solver.Solver(
        loader=loader,
        loss=loss,
        learner=learner,
        optimizer=optimizer,
        schedulers=[],
        dictionary=dictionary,
        verbose=verbose,
    )
    return solver


def build_sgns_solver(
        cooccurrence_path
        save_embeddings_dir,
        k=15,                   # SGNS option
        undersampling=2.45e-5,  # SGNS option
        smoothing=0.75,         # SGNS option
        shard_factor=1,         # Dense option
        bias=False,
        init_embeddings_path=None,
        dimensions=300,
        learning_rate=0.01,
        opt_str='adam',
        num_writes=100,
        num_updates=100000,
        #batch_size,
        seed=1917,
        device=None,
        verbose=True,
    ):

    np.random.seed(seed)
    torch.random.manual_seed(seed)

    dictionary = h.dictionary.Dictionary.load(
        os.path.join(cooccurrence_path, 'dictionary'))

    loss = h.loss.SGNSLoss(ncomponents=len(dictionary)**2, k=k)

    learner = h.learner.DenseLearner(
        vocab=len(dictionary),
        covocab=len(dictionary),
        d=d,
        bias=bias,
        init=get_init_embs(init_embeddings_path, device),
        device=device
    )

    loader = h.loader.DenseLoader(
        cooccurrence_path,
        shard_factor,
        include_unigrams=loss.INCLUDE_UNIGRAMS,
        undersampling=undersampling,
        smoothing=smoothing,
        device=device
        verbose=verbose,
    )

    optimizer = get_optimizer(opt_str, learner.parameters(), learning_rate)

    solver = h.solver.Solver(
        loader=loader,
        loss=loss,
        learner=learner,
        optimizer=optimizer,
        schedulers=[],
        dictionary=dictionary,
        verbose=verbose,
    )
    return solver



def build_glove_solver(
        cooccurrence_path
        save_embeddings_dir,
        X_max=100,      # Glove option
        alpha=3/4,      # Glove option
        shard_factor=1, # Dense option
        bias=True,
        init_embeddings_path=None,
        dimensions=300,
        learning_rate=0.01,
        opt_str='adam',
        num_writes=100,
        num_updates=100000,
        #batch_size,
        seed=1917,
        device=None,
        verbose=True,
    ):

    np.random.seed(seed)
    torch.random.manual_seed(seed)

    dictionary = h.dictionary.Dictionary.load(
        os.path.join(cooccurrence_path, 'dictionary'))

    learner = h.learner.DenseLearner(
        vocab=len(dictionary),
        covocab=len(dictionary),
        d=d,
        bias=bias,
        init=get_init_embs(init_embeddings_path, device),
        device=device
    )

    loader = h.loader.DenseLoader(
        cooccurrence_path,
        shard_factor,
        include_unigrams=learner.INCLUDE_UNIGRAMS,
        device=device
        verbose=verbose,
    ):

    loss = h.loss.GloveLoss(
        ncomponents=len(dictionary)**2, X_max=100, alpha=3/4):

    optimizer = get_optimizer(opt_str, learner.parameters(), learning_rate)

    solver = h.solver.Solver(
        loader=loader,
        loss=loss,
        learner=learner,
        optimizer=optimizer,
        schedulers=[],
        dictionary=dictionary,
        verbose=verbose,
    )
    return solver

