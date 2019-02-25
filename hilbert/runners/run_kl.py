import hilbert.factories as proletariat
from hilbert.runners.run_base import init_and_run, modify_args, get_base_argparser


def run_kl(
        bigram_path,
        save_embeddings_dir,
        epochs=100,
        iters_per_epoch=100,
        init_embeddings_path=None,
        d=300,
        temperature=1,
        update_density=1.,
        mask_diagonal=False,
        learning_rate=0.01,
        opt_str='adam',
        sector_factor=1,
        shard_factor=1,
        shard_times=1,
        seed=1,
        device=None,
    ):

    embsolver = proletariat.construct_KL_solver(
        bigram_path=bigram_path, init_embeddings_path=init_embeddings_path,
        d=d, temperature=temperature, update_density=update_density,
        mask_diagonal=mask_diagonal, learning_rate=learning_rate,
        opt_str=opt_str, shard_factor=shard_factor,
        sector_factor=sector_factor, seed=seed, device=device
    )
    init_and_run(embsolver, epochs, iters_per_epoch, shard_times, save_embeddings_dir)


if __name__ == '__main__':

    base_parser = get_base_argparser()
    base_parser.add_argument(
        '--temperature', '-t', type=float, default=1, dest='temperature',
        help=(
            "equalizes weighting for loss from individual token pairs.  "
            "Use temperature > 1 for more equal weights."
        )
    )
    all_args = vars(base_parser.parse_args())
    modify_args(all_args)
    run_kl(**all_args)


"""
Example command:
python run_kl.py -u 1.0 -l 0.01 -s adam -I 100 --init
    std-w2v-s1-t1-v10k-iter5/vectors-init --epochs 150 --seed 1 --bigram
    5w-dynamic-10k/thresh1 -t 1 -o testkl
"""

