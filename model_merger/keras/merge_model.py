import keras.engine.training
from keras.layers import Input, Dense
from keras.layers import Concatenate
from keras.optimizers import Optimizer, SGD
from keras.models import Model
from typing import List, Union, Optional, Tuple
from network_model.model_base.tempload import builder_for_merge
from model_merger.keras.type import Merge, Loss, TrainableModelIndex
from util.keras_version import is_new_keras


class ModelMerger:

    def __init__(self,
                 merge_obj: Merge,
                 loss: Loss = "categorical_crossentropy",
                 optimizer: Optimizer = SGD(),
                 metrics: Optional[List[str]] = None,
                 output_activation: str = "softmax"):
        if metrics is None:
            metrics = ['accuracy']
        self.__loss = loss
        self.__optimizer = optimizer
        self.__metrics = metrics
        self.__merge_obj = merge_obj
        self.__output_activation = output_activation

    @staticmethod
    def set_model_trainable(base_model: keras.engine.training.Model,
                            trainable: TrainableModelIndex) -> keras.engine.training.Model:
        if type(trainable) is bool:
            base_model.trainable = trainable
            return base_model
        for layer in base_model.layers[:trainable]:
            layer.trainable = False
        return base_model

    @property
    def optimizer(self) -> Optimizer:
        return self.__optimizer

    @property
    def metrics(self) -> List[str]:
        return self.__metrics

    @property
    def merge(self) -> Merge:
        return self.__merge_obj

    @property
    def loss(self) -> Loss:
        return self.__loss

    @property
    def output_activation(self):
        return self.__output_activation

    def get_output_num(self, model: keras.engine.training.Model, output_num: Optional[int] = None):
        if output_num is None:
            return model.output_shape[-1]
        if type(self.merge) is Concatenate:
            return output_num
        return model.output_shape[-1]

    def merge_models(self,
                     models: List[keras.engine.training.Model],
                     output_num: Optional[int] = None,
                     middle_layer_neuro_nums: Optional[List[Tuple[int, str]]] = None) -> keras.engine.training.Model:
        input_shape = tuple(models[0].input_shape[1:])
        print(input_shape)
        output_class_num = models[0].output_shape[-1] if output_num is None else output_num
        print(output_class_num)
        input_layer = Input(shape=input_shape)
        model_outputs = [model(input_layer) for model in models]
        added_model_output = self.merge(model_outputs)
        if middle_layer_neuro_nums is None:
            output = Dense(output_class_num, activation=self.output_activation)(added_model_output)
            model = Model(input_layer, output)
            # モデルの概要を表示
            return self.compile(model)
        add_layers = middle_layer_neuro_nums + [(output_class_num, self.output_activation)]
        print(add_layers)
        output = Dense(add_layers[0][0], activation=add_layers[0][1])(added_model_output)
        for params in add_layers[1:]:
            print(params)
            output = Dense(params[0], activation=params[1])(output)
        model = Model(input_layer, output)
        return self.compile(model)

    def compile(self, model):
        print("compile model type", type(model))
        model.summary()
        # モデルをコンパイル
        model.compile(loss=self.loss, optimizer=self.optimizer, metrics=self.metrics)
        model.metrics_name=self.metrics
        print("compiled model type:", type(model))
        return model

    def merge_models_separately_input(self,
                                      models: List[keras.engine.training.Model],
                                      output_num: Optional[int] = None,
                                      middle_layer_neuro_nums: Optional[List[Tuple[int, str]]] = None) -> keras.engine.training.Model:
        models = add_layer_name_for_models(models)
        input_layer = [model.input for model in models]
        model_outputs = [model.output for model in models]
        output_class_num = models[0].output_shape[-1] if output_num is None else output_num
        added_model_output = self.merge(model_outputs)
        if middle_layer_neuro_nums is None:
            output = Dense(output_class_num, activation=self.output_activation)(added_model_output)
            model = Model(input_layer, [output])
            return self.compile(model)
        add_layers = middle_layer_neuro_nums + [(output_class_num, self.output_activation)]
        print(add_layers)
        output = Dense(add_layers[0][0], activation=add_layers[0][1])(added_model_output)
        for params in add_layers[1:]:
            print(params)
            output = Dense(params[0], activation=params[1])(output)
        model = Model(input_layer, [output])
        return self.compile(model)

    def merge_models_from_model_files(self,
                                      h5_paths: List[Union[str, Tuple[str, str]]],
                                      trainable_model: Union[TrainableModelIndex, List[TrainableModelIndex]] = True,
                                      output_num: Optional[int] = None,
                                      middle_layer_neuro_nums: Optional[List[Tuple[int, str]]] = None,
                                      merge_per_model_name: str = 'model') -> keras.engine.training.Model:
        models = [builder_for_merge(h5_path) for h5_path in h5_paths]
        are_trainable_models = trainable_model if type(trainable_model) is list else [trainable_model for _ in h5_paths]
        for index, (model, is_trainable) in enumerate(zip(models, are_trainable_models)):
            if is_new_keras():
                model._name = merge_per_model_name + str(index)
            else:
                model.name = merge_per_model_name + str(index)
            self.set_model_trainable(model, is_trainable)
        return self.merge_models(models, output_num, middle_layer_neuro_nums)


def add_layer_name_to_index(model: keras.engine.training.Model, index: int):
    for layer in model.layers:
        layer._name = layer.name + "_" + str(index)
    return model


def add_layer_name_for_models(models: List[keras.engine.training.Model]):
    for index, model in enumerate(models):
        add_layer_name_to_index(model, index)
    return models
