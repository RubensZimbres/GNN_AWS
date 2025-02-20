"""
    Copyright 2023 Contributors

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
from unittest.mock import patch, MagicMock
import operator

import torch as th
from numpy.testing import assert_equal, assert_almost_equal
import dgl

from graphstorm.eval import GSgnnMrrLPEvaluator
from graphstorm.eval import GSgnnAccEvaluator
from graphstorm.eval import GSgnnRegressionEvaluator
from graphstorm.eval.evaluator import early_stop_avg_increase_judge
from graphstorm.eval.evaluator import early_stop_cons_increase_judge
from graphstorm.config.config import EARLY_STOP_AVERAGE_INCREASE_STRATEGY
from graphstorm.config.config import EARLY_STOP_CONSECUTIVE_INCREASE_STRATEGY

from util import Dummy

def gen_hg():
    num_nodes_dict = {
        "n0": 100,
        "n1": 100,
    }

    edges = {
        ("n0", "r0", "n1"): (th.randint(100, (100,)), th.randint(100, (100,))),
        ("n0", "r1", "n1"): (th.randint(100, (200,)), th.randint(100, (200,))),
    }

    hg = dgl.heterograph(edges, num_nodes_dict=num_nodes_dict)
    return hg

def test_mrr_lp_evaluator():
    # system heavily depends on th distributed
    dist_init_method = 'tcp://{master_ip}:{master_port}'.format(
        master_ip='127.0.0.1', master_port='12346')
    th.distributed.init_process_group(backend="gloo",
                                      init_method=dist_init_method,
                                      world_size=1,
                                      rank=0)
    # common Dummy objects
    train_data = Dummy({
            "train_idxs": th.randint(10, (10,)),
            "val_idxs": th.randint(10, (10,)),
            "test_idxs": th.randint(10, (10,)),
            "do_validation": True
        })

    config = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 100,
            "enable_early_stop": False,
        })

    # test compute_score
    val_pos_scores = th.rand((10,1))
    val_neg_scores = th.rand((10,10))
    val_scores = {
        ("u", "r0", "v") : [(val_pos_scores, val_neg_scores / 2), (val_pos_scores, val_neg_scores / 2)],
        ("u", "r1", "v") : [(val_pos_scores, val_neg_scores / 4)]
    }
    test_pos_scores = th.rand((10,1))
    test_neg_scores = th.rand((10,10))
    test_scores = {
        ("u", "r0", "v") : [(test_pos_scores, test_neg_scores / 2), (test_pos_scores, test_neg_scores / 2)],
        ("u", "r1", "v") : [(test_pos_scores, test_neg_scores / 4)]
    }

    lp = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                             train_data,
                             num_negative_edges_eval=config.num_negative_edges_eval,
                             use_dot_product=config.use_dot_product,
                             enable_early_stop=config.enable_early_stop)
    val_s = lp.compute_score(val_scores)
    test_s = lp.compute_score(test_scores)
    val_sc, test_sc = lp.evaluate(val_scores, test_scores, 0)
    assert_equal(val_s['mrr'], val_sc['mrr'])
    assert_equal(test_s['mrr'], test_sc['mrr'])

    rank = []
    for i in range(len(val_pos_scores)):
        val_pos = val_pos_scores[i]
        val_neg0 = val_neg_scores[i] / 2
        val_neg1 = val_neg_scores[i] / 4
        scores = th.cat([val_pos, val_neg0])
        _, indices = th.sort(scores, descending=True)
        ranking = th.nonzero(indices == 0) + 1
        rank.append(ranking.cpu().detach())
        rank.append(ranking.cpu().detach())
        scores = th.cat([val_pos, val_neg1])
        _, indices = th.sort(scores, descending=True)
        ranking = th.nonzero(indices == 0) + 1
        rank.append(ranking.cpu().detach())
    rank = th.cat(rank, dim=0)
    mrr = 1.0/rank
    mrr = th.sum(mrr) / len(mrr)
    assert_almost_equal(val_s['mrr'], mrr.numpy(), decimal=7)

    rank = []
    for i in range(len(test_pos_scores)):
        val_pos = test_pos_scores[i]
        val_neg0 = test_neg_scores[i] / 2
        val_neg1 = test_neg_scores[i] / 4
        scores = th.cat([val_pos, val_neg0])
        _, indices = th.sort(scores, descending=True)
        ranking = th.nonzero(indices == 0) + 1
        rank.append(ranking.cpu().detach())
        rank.append(ranking.cpu().detach())
        scores = th.cat([val_pos, val_neg1])
        _, indices = th.sort(scores, descending=True)
        ranking = th.nonzero(indices == 0) + 1
        rank.append(ranking.cpu().detach())
    rank = th.cat(rank, dim=0)
    mrr = 1.0/rank
    mrr = th.sum(mrr) / len(mrr)
    assert_almost_equal(test_s['mrr'], mrr.numpy(), decimal=7)

    # test evaluate
    @patch.object(GSgnnMrrLPEvaluator, 'compute_score')
    def check_evaluate(mock_compute_score):
        lp = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                 train_data,
                                 num_negative_edges_eval=config. num_negative_edges_eval,
                                 use_dot_product=config.use_dot_product,
                                 enable_early_stop=config.enable_early_stop)

        mock_compute_score.side_effect = [
            {"mrr": 0.6},
            {"mrr": 0.7},
            {"mrr": 0.65},
            {"mrr": 0.8},
            {"mrr": 0.8},
            {"mrr": 0.7}
        ]

        val_score, test_score = lp.evaluate(
            {("u", "b", "v") : ()}, {("u", "b", "v") : ()}, 100)
        assert val_score["mrr"] == 0.7
        assert test_score["mrr"] == 0.6
        val_score, test_score = lp.evaluate(
            {("u", "b", "v") : ()}, {("u", "b", "v") : ()}, 200)
        assert val_score["mrr"] == 0.8
        assert test_score["mrr"] == 0.65
        val_score, test_score = lp.evaluate(
            {("u", "b", "v") : ()}, {("u", "b", "v") : ()}, 300)
        assert val_score["mrr"] == 0.7
        assert test_score["mrr"] == 0.8

        assert lp.best_val_score["mrr"] == 0.8
        assert lp.best_test_score["mrr"] == 0.65
        assert lp.best_iter_num["mrr"] == 200

    # check GSgnnMrrLPEvaluator.evaluate()
    check_evaluate()

    # common Dummy objects
    train_data = Dummy({
            "train_idxs": None,
            "val_idxs": None,
            "test_idxs": th.randint(10, (10,)),
            "do_validation": True
        })
    # test evaluate
    @patch.object(GSgnnMrrLPEvaluator, 'compute_score')
    def check_evaluate_infer(mock_compute_score):
        lp = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                 train_data,
                                 num_negative_edges_eval=config.num_negative_edges_eval,
                                 use_dot_product=config.use_dot_product,
                                 enable_early_stop=config.enable_early_stop)

        mock_compute_score.side_effect = [
            {"mrr": 0.6},
            {"mrr": 0.7},
        ]

        val_score, test_score = lp.evaluate(None, None, 100)
        assert val_score["mrr"] == -1
        assert test_score["mrr"] == 0.6
        val_score, test_score = lp.evaluate(None, None, 200)
        assert val_score["mrr"] == -1
        assert test_score["mrr"] == 0.7

        assert lp.best_val_score["mrr"] == 0 # Still initial value 0
        assert lp.best_test_score["mrr"] == 0 # Still initial value 0
        assert lp.best_iter_num["mrr"] == 0 # Still initial value 0

    # check GSgnnMrrLPEvaluator.evaluate()
    check_evaluate_infer()

    # check GSgnnMrrLPEvaluator.do_eval()
    # train_data.do_validation True
    # config.no_validation False
    lp = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                             train_data,
                             num_negative_edges_eval=config.num_negative_edges_eval,
                             use_dot_product=config.use_dot_product,
                             enable_early_stop=config.enable_early_stop)
    assert lp.do_eval(120, epoch_end=True) is True
    assert lp.do_eval(200) is True
    assert lp.do_eval(0) is True
    assert lp.do_eval(1) is False

    config3 = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 0,
            "enable_early_stop": False,
        })

    # train_data.do_validation True
    # config.no_validation False
    # evaluation_frequency is 0
    lp = GSgnnMrrLPEvaluator(config3.evaluation_frequency,
                             train_data,
                             num_negative_edges_eval=config3.num_negative_edges_eval,
                             use_dot_product=config3.use_dot_product,
                             enable_early_stop=config3.enable_early_stop)
    assert lp.do_eval(120, epoch_end=True) is True
    assert lp.do_eval(200) is False

    th.distributed.destroy_process_group()

def test_acc_evaluator():
    # system heavily depends on th distributed
    dist_init_method = 'tcp://{master_ip}:{master_port}'.format(
        master_ip='127.0.0.1', master_port='12346')
    th.distributed.init_process_group(backend="gloo",
                                      init_method=dist_init_method,
                                      world_size=1,
                                      rank=0)

    config = Dummy({
            "multilabel": False,
            "evaluation_frequency": 100,
            "eval_metric": ["accuracy"],
            "enable_early_stop": False,
        })

    # Test evaluate
    @patch.object(GSgnnAccEvaluator, 'compute_score')
    def check_evaluate(mock_compute_score):
        nc = GSgnnAccEvaluator(config.evaluation_frequency,
                               config.eval_metric,
                               config.multilabel,
                               config.enable_early_stop)
        mock_compute_score.side_effect = [
            {"accuracy": 0.7},
            {"accuracy": 0.65},
            {"accuracy": 0.8},
            {"accuracy": 0.7},
            {"accuracy": 0.76},
            {"accuracy": 0.8},
        ]
        val_score, test_score = nc.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 100)
        mock_compute_score.assert_called()
        assert val_score["accuracy"] == 0.7
        assert test_score["accuracy"] == 0.65

        val_score, test_score = nc.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 200)
        mock_compute_score.assert_called()
        assert val_score["accuracy"] == 0.8
        assert test_score["accuracy"] == 0.7

        val_score, test_score = nc.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 300)
        mock_compute_score.assert_called()
        assert val_score["accuracy"] == 0.76
        assert test_score["accuracy"] == 0.8

        assert nc.best_val_score["accuracy"] == 0.8
        assert nc.best_test_score["accuracy"] == 0.7
        assert nc.best_iter_num["accuracy"] == 200

    check_evaluate()

    # check GSgnnAccEvaluator.do_eval()
    # train_data.do_validation True
    # config.no_validation False
    nc = GSgnnAccEvaluator(config.evaluation_frequency,
                           config.eval_metric,
                           config.multilabel,
                           config.enable_early_stop)
    assert nc.do_eval(120, epoch_end=True) is True
    assert nc.do_eval(200) is True
    assert nc.do_eval(0) is True
    assert nc.do_eval(1) is False

    config3 = Dummy({
            "multilabel": False,
            "evaluation_frequency": 0,
            "eval_metric": ["accuracy"],
            "enable_early_stop": False,
        })

    # train_data.do_validation True
    # config.no_validation False
    # evaluation_frequency is 0
    nc = GSgnnAccEvaluator(config3.evaluation_frequency,
                           config3.eval_metric,
                           config3.multilabel,
                           config3.enable_early_stop)
    assert nc.do_eval(120, epoch_end=True) is True
    assert nc.do_eval(200) is False
    th.distributed.destroy_process_group()

def test_regression_evaluator():
    # system heavily depends on th distributed
    dist_init_method = 'tcp://{master_ip}:{master_port}'.format(
        master_ip='127.0.0.1', master_port='12346')
    th.distributed.init_process_group(backend="gloo",
                                      init_method=dist_init_method,
                                      world_size=1,
                                      rank=0)

    config = Dummy({
            "evaluation_frequency": 100,
            "eval_metric": ["rmse"],
            "enable_early_stop": False,
        })

    # Test evaluate
    @patch.object(GSgnnRegressionEvaluator, 'compute_score')
    def check_evaluate(mock_compute_score):
        nr = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                      config.eval_metric,
                                      config.enable_early_stop)
        mock_compute_score.side_effect = [
            {"rmse": 0.7},
            {"rmse": 0.8},
            {"rmse": 0.2},
            {"rmse": 0.23},
            {"rmse": 0.3},
            {"rmse": 0.31},
        ]

        val_score, test_score = nr.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 100)
        mock_compute_score.assert_called()
        assert val_score["rmse"] == 0.7
        assert test_score["rmse"] == 0.8

        val_score, test_score = nr.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 300)
        mock_compute_score.assert_called()
        assert val_score["rmse"] == 0.2
        assert test_score["rmse"] == 0.23

        val_score, test_score = nr.evaluate(th.rand((10,)), th.rand((10,)), th.rand((10,)), th.rand((10,)), 500)
        mock_compute_score.assert_called()
        assert val_score["rmse"] == 0.3
        assert test_score["rmse"] == 0.31

        assert nr.best_val_score["rmse"] == 0.2
        assert nr.best_test_score["rmse"] == 0.23
        assert nr.best_iter_num["rmse"] == 300

    check_evaluate()

    # check GSgnnRegressionEvaluator.do_eval()
    # train_data.do_validation True
    nr = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                  config.eval_metric,
                                  config.enable_early_stop)
    assert nr.do_eval(120, epoch_end=True) is True
    assert nr.do_eval(200) is True
    assert nr.do_eval(0) is True
    assert nr.do_eval(1) is False

    config3 = Dummy({
            "evaluation_frequency": 0,
            "no_validation": False,
            "eval_metric": ["rmse"],
            "enable_early_stop": False,
        })

    # train_data.do_validation True
    # evaluation_frequency is 0
    nr = GSgnnRegressionEvaluator(config3.evaluation_frequency,
                                  config3.eval_metric,
                                  config3.enable_early_stop)
    assert nr.do_eval(120, epoch_end=True) is True
    assert nr.do_eval(200) is False
    th.distributed.destroy_process_group()

def test_early_stop_avg_increase_judge():
    comparator = operator.le
    val_score = 0.5
    val_perf_list = [0.4, 0.45, 0.6]
    assert early_stop_avg_increase_judge(val_score, val_perf_list, comparator) is False
    val_score = 0.4
    assert early_stop_avg_increase_judge(val_score, val_perf_list, comparator)

    comparator = operator.ge
    val_score = 0.4
    val_perf_list = [0.4, 0.45, 0.6]
    assert early_stop_avg_increase_judge(val_score, val_perf_list, comparator) is False
    val_score = 0.5
    assert early_stop_avg_increase_judge(val_score, val_perf_list, comparator)

def test_early_stop_cons_increase_judge():
    comparator = operator.le
    val_score = 0.5
    val_perf_list = [0.6, 0.45, 0.6]
    assert early_stop_cons_increase_judge(val_score, val_perf_list, comparator) is False
    val_score = 0.4
    assert early_stop_cons_increase_judge(val_score, val_perf_list, comparator)

    comparator = operator.ge
    val_score = 0.5
    val_perf_list = [0.45, 0.45, 0.55]
    assert early_stop_cons_increase_judge(val_score, val_perf_list, comparator) is False
    val_score = 0.55
    assert early_stop_cons_increase_judge(val_score, val_perf_list, comparator)

def test_early_stop_evaluator():
    # common Dummy objects
    config = Dummy({
            "evaluation_frequency": 100,
            "eval_metric": ["rmse"],
            "enable_early_stop": False,
            "call_to_consider_early_stop": 5,
            "window_for_early_stop": 3,
            "early_stop_strategy": EARLY_STOP_CONSECUTIVE_INCREASE_STRATEGY,
        })

    evaluator = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                         config.eval_metric,
                                         config.enable_early_stop,
                                         config.call_to_consider_early_stop,
                                         config.window_for_early_stop,
                                         config.early_stop_strategy)
    for _ in range(10):
        # always return false
        assert evaluator.do_early_stop({"rmse": 0.1}) is False

    config = Dummy({
            "evaluation_frequency": 100,
            "eval_metric": ["rmse"],
            "enable_early_stop": True,
            "call_to_consider_early_stop": 5,
            "window_for_early_stop": 3,
            "early_stop_strategy": EARLY_STOP_CONSECUTIVE_INCREASE_STRATEGY,
        })

    evaluator = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                         config.eval_metric,
                                         config.enable_early_stop,
                                         config.call_to_consider_early_stop,
                                         config.window_for_early_stop,
                                         config.early_stop_strategy)
    for _ in range(5):
        # always return false
        assert evaluator.do_early_stop({"rmse": 0.5}) is False

    for _ in range(3):
        # no enough data point
        assert evaluator.do_early_stop({"rmse": 0.4}) is False

    assert evaluator.do_early_stop({"rmse": 0.3}) is False # better result
    assert evaluator.do_early_stop({"rmse": 0.32}) is False
    assert evaluator.do_early_stop({"rmse": 0.3}) is False
    assert evaluator.do_early_stop({"rmse": 0.32}) # early stop

    config2 = Dummy({
            "multilabel": False,
            "evaluation_frequency": 100,
            "eval_metric": ["accuracy"],
            "enable_early_stop": True,
            "call_to_consider_early_stop": 5,
            "window_for_early_stop": 3,
            "early_stop_strategy": EARLY_STOP_AVERAGE_INCREASE_STRATEGY,
        })

    evaluator = GSgnnAccEvaluator(config2.evaluation_frequency,
                                  config2.eval_metric,
                                  config2.multilabel,
                                  config2.enable_early_stop,
                                  config2.call_to_consider_early_stop,
                                  config2.window_for_early_stop,
                                  config2.early_stop_strategy)
    for _ in range(5):
        # always return false
        assert evaluator.do_early_stop({"accuracy": 0.5}) is False

    for _ in range(3):
        # no enough data point
        assert evaluator.do_early_stop({"accuracy": 0.6}) is False

    assert evaluator.do_early_stop({"accuracy": 0.7}) is False # better than average
    assert evaluator.do_early_stop({"accuracy": 0.68}) is False # still better
    assert evaluator.do_early_stop({"accuracy": 0.66}) # early stop

def test_early_stop_lp_evaluator():
    # common Dummy objects
    train_data = Dummy({
            "train_idxs": th.randint(10, (10,)),
            "val_idxs": th.randint(10, (10,)),
            "test_idxs": th.randint(10, (10,)),
            "do_validation": True
        })

    config = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 100,
            "enable_early_stop": False,
        })
    evaluator = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                    train_data,
                                    num_negative_edges_eval=config.num_negative_edges_eval,
                                    use_dot_product=config.use_dot_product,
                                    enable_early_stop=config.enable_early_stop)
    for _ in range(10):
        # always return false
        assert evaluator.do_early_stop({"mrr": 0.5}) is False

    config = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 100,
            "enable_early_stop": True,
            "call_to_consider_early_stop": 5,
            "window_for_early_stop": 3,
            "early_stop_strategy": EARLY_STOP_CONSECUTIVE_INCREASE_STRATEGY,
        })
    evaluator = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                    train_data,
                                    num_negative_edges_eval=config.num_negative_edges_eval,
                                    use_dot_product=config.use_dot_product,
                                    enable_early_stop=config.enable_early_stop,
                                    call_to_consider_early_stop=config.call_to_consider_early_stop,
                                    window_for_early_stop=config.window_for_early_stop,
                                    early_stop_strategy=config.early_stop_strategy)
    for _ in range(5):
        # always return false
        assert evaluator.do_early_stop({"mrr": 0.5}) is False

    for _ in range(3):
        # no enough data point
        assert evaluator.do_early_stop({"mrr": 0.4}) is False

    assert evaluator.do_early_stop({"mrr": 0.5}) is False # better result
    assert evaluator.do_early_stop({"mrr": 0.45}) is False
    assert evaluator.do_early_stop({"mrr": 0.45}) is False
    assert evaluator.do_early_stop({"mrr": 0.45}) # early stop

    config = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 100,
            "enable_early_stop": True,
            "call_to_consider_early_stop": 5,
            "window_for_early_stop": 3,
            "early_stop_strategy": EARLY_STOP_AVERAGE_INCREASE_STRATEGY,
        })
    evaluator = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                    train_data,
                                    num_negative_edges_eval=config.num_negative_edges_eval,
                                    use_dot_product=config.use_dot_product,
                                    enable_early_stop=config.enable_early_stop,
                                    call_to_consider_early_stop=config.call_to_consider_early_stop,
                                    window_for_early_stop=config.window_for_early_stop,
                                    early_stop_strategy=config.early_stop_strategy)
    for _ in range(5):
        # always return false
        assert evaluator.do_early_stop({"accuracy": 0.5}) is False

    for _ in range(3):
        # no enough data point
        assert evaluator.do_early_stop({"accuracy": 0.6}) is False

    assert evaluator.do_early_stop({"accuracy": 0.7}) is False # better than average
    assert evaluator.do_early_stop({"accuracy": 0.68}) is False # still better
    assert evaluator.do_early_stop({"accuracy": 0.66})

def test_get_val_score_rank():
    # ------------------- test InstanceEvaluator -------------------
    # common Dummy objects
    config = Dummy({
            "multilabel": False,
            "evaluation_frequency": 100,
            "eval_metric": ["accuracy"],
            "enable_early_stop": False,
        })

    evaluator = GSgnnAccEvaluator(config.evaluation_frequency,
                                  config.eval_metric,
                                  config.multilabel,
                                  config.enable_early_stop)
    # For accuracy, the bigger the better.
    val_score = {"accuracy": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"accuracy": 0.40}
    assert evaluator.get_val_score_rank(val_score) == 2
    val_score = {"accuracy": 0.7}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"accuracy": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 3

    config = Dummy({
            "multilabel": False,
            "evaluation_frequency": 100,
            "eval_metric": ["mse"],
            "enable_early_stop": False,
        })

    evaluator = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                         config.eval_metric,
                                         config.enable_early_stop)
    # For mse, the smaller the better
    val_score = {"mse": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"mse": 0.40}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"mse": 0.7}
    assert evaluator.get_val_score_rank(val_score) == 3
    val_score = {"mse": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 3

    config = Dummy({
            "multilabel": False,
            "evaluation_frequency": 100,
            "eval_metric": ["rmse"],
            "enable_early_stop": False,
        })

    evaluator = GSgnnRegressionEvaluator(config.evaluation_frequency,
                                         config.eval_metric,
                                         config.enable_early_stop)
    # For rmse, the smaller the better
    val_score = {"rmse": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"rmse": 0.40}
    assert evaluator.get_val_score_rank(val_score) == 1
    val_score = {"rmse": 0.7}
    assert evaluator.get_val_score_rank(val_score) == 3
    val_score = {"rmse": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 3

    # ------------------- test LPEvaluator -------------------
    # common Dummy objects
    train_data = Dummy({
            "train_idxs": th.randint(10, (10,)),
            "val_idxs": th.randint(10, (10,)),
            "test_idxs": th.randint(10, (10,)),
        })

    config = Dummy({
            "num_negative_edges_eval": 10,
            "use_dot_product": True,
            "evaluation_frequency": 100,
            "enable_early_stop": False,
            "eval_metric": ["mrr"]
        })

    evaluator = GSgnnMrrLPEvaluator(config.evaluation_frequency,
                                    train_data,
                                    num_negative_edges_eval=config.num_negative_edges_eval,
                                    use_dot_product=config.use_dot_product,
                                    enable_early_stop=config.enable_early_stop)

    # For MRR, the bigger the better
    val_score = {"mrr": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 1

    val_score = {"mrr": 0.40}
    assert evaluator.get_val_score_rank(val_score) == 2

    val_score = {"mrr": 0.7}
    assert evaluator.get_val_score_rank(val_score) == 1

    val_score = {"mrr": 0.47}
    assert evaluator.get_val_score_rank(val_score) == 3


if __name__ == '__main__':
    # test evaluators
    test_mrr_lp_evaluator()
    test_acc_evaluator()
    test_regression_evaluator()
    test_early_stop_avg_increase_judge()
    test_early_stop_cons_increase_judge()
    test_early_stop_evaluator()
    test_early_stop_lp_evaluator()
    test_get_val_score_rank()
