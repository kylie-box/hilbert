import hilbert.factories as proletariat
from hilbert.runners.run_base import init_and_run, modify_args, get_base_argparser, kw_filter

def run_glv(
        bigram_path,
        save_embeddings_dir,
        X_max=100,
        alpha=0.75,
        nobias=False,
        **kwargs
    ):

    embsolver = proletariat.construct_glv_solver(
        bigram_path=bigram_path,
        alpha=alpha,
        X_max=X_max,
        nobias=nobias,
        **kw_filter(kwargs)
    )
    init_and_run(embsolver,
                 kwargs['epochs'],
                 kwargs['iters_per_epoch'],
                 kwargs['shard_times'],
                 save_embeddings_dir)


if __name__ == '__main__':

    base_parser = get_base_argparser()
    base_parser.add_argument(
        '--X-max', '-x', type=float, default=100, dest='X_max',
        help="xmax in glove weighting function"
    )
    base_parser.add_argument(
        '--alpha', '-a', type=float, default=3/4,
        help="exponent in the weighting function for glove"
    )
    base_parser.add_argument(
        '--nobias', action='store_true',
        help='set this flag to override GloVe defaults and remove bias learning' 
    )
    all_args = vars(base_parser.parse_args())
    modify_args(all_args)
    run_glv(**all_args)
