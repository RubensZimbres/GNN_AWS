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

    Infer wrapper for edge classification and regression.
"""
import time
import os
import torch as th

from .graphstorm_infer import GSInfer
from ..model.utils import save_embeddings as save_gsgnn_embeddings
from ..model.gnn import do_full_graph_inference
from ..model.edge_gnn import edge_mini_batch_predict

from ..utils import sys_tracker

class GSgnnEdgePredictionInfer(GSInfer):
    """ Edge classification/regression infer.

    This is a highlevel infer wrapper that can be used directly
    to do edge classification/regression model inference.

    Parameters
    ----------
    model : GSgnnNodeModel
        The GNN model for node prediction.
    rank : int
        The rank.
    """

    def infer(self, loader, save_embed_path, save_predict_path=None,
            mini_batch_infer=False):  # pylint: disable=unused-argument
        """ Do inference

        The infer can do three things:
        1. (Optional) Evaluate the model performance on a test set if given
        2. Generate node embeddings

        Parameters
        ----------
        loader : GSEdgeDataLoader
            The mini-batch sampler for edge prediction task.
        save_embed_path : str
            The path where the GNN embeddings will be saved.
        save_predict_path : str
            The path where the prediction results will be saved.
        mini_batch_infer : bool
            Whether or not to use mini-batch inference.
        """
        do_eval = self.evaluator is not None
        sys_tracker.check('start inferencing')
        self._model.eval()
        embs = do_full_graph_inference(self._model, loader.data,
                                       task_tracker=self.task_tracker)
        sys_tracker.check('compute embeddings')
        res = edge_mini_batch_predict(self._model, embs, loader, return_label=do_eval)
        pred = res[0]
        label = res[1] if do_eval else None
        sys_tracker.check('compute prediction')

        # Only save the embeddings related to target edge types.
        infer_data = loader.data
        target_ntypes = set()
        for etype in infer_data.eval_etypes:
            target_ntypes.add(etype[0])
            target_ntypes.add(etype[2])
        embs = {ntype: embs[ntype] for ntype in target_ntypes}
        if save_embed_path is not None:
            save_gsgnn_embeddings(save_embed_path, embs, self.rank,
                th.distributed.get_world_size())
        th.distributed.barrier()
        sys_tracker.check('save embeddings')

        if save_predict_path is not None:
            os.makedirs(save_predict_path, exist_ok=True)
            th.save(pred, os.path.join(save_predict_path, "predict-{}.pt".format(self.rank)))
        th.distributed.barrier()
        sys_tracker.check('save predictions')

        if do_eval:
            test_start = time.time()
            val_score, test_score = self.evaluator.evaluate(pred, pred, label, label, 0)
            sys_tracker.check('run evaluation')
            if self.rank == 0:
                self.log_print_metrics(val_score=val_score,
                                       test_score=test_score,
                                       dur_eval=time.time() - test_start,
                                       total_steps=0)
