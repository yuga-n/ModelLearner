import keras.callbacks
from keras.callbacks import CallbackList, ProgbarLogger, BaseLogger, History
from keras.utils.data_utils import GeneratorEnqueuer
from keras.utils.generic_utils import to_list
from keras.preprocessing.image import ImageDataGenerator
import numpy as np
from network_model.generator import DataLoaderFromPaths
from network_model.generator import DataLoaderFromPathsWithDataAugmentation
from typing import List
from typing import Tuple
from typing import Optional
from typing import Union
from typing import Callable
import os
from datetime import datetime
from DataIO import data_loader as dl
from network_model.abstract_model import AbstractModel, build_record_path, ModelPreProcessor


class Model(AbstractModel):

    def __init__(self,
                 model_base: keras.engine.training.Model,
                 class_set: List[str],
                 callbacks: Optional[List[keras.callbacks.Callback]] = None,
                 monitor: str = "",
                 will_save_h5: bool = True,
                 preprocess_for_model: ModelPreProcessor = None,
                 after_learned_process: Optional[Callable[[None], None]] = None):
        """

        :param model_base: kerasで構築したモデル
        :param class_set: クラスの元となったリスト
        :param callbacks: モデルに渡すコールバック関数
        :param monitor: モデルの途中で記録するパラメータ　デフォルトだと途中で記録しない
        :param will_save_h5: 途中モデル読み込み時に旧式のh5ファイルで保存するかどうか　デフォルトだと保存する
        :param preprocess_for_model: モデル学習前にモデルに対してする処理
        :param after_learned_process: モデル学習後の後始末
        """
        self.__model = model_base
        shape = model_base.input[0].shape.as_list() if type(model_base.input) is list else model_base.input.shape.as_list()
        super().__init__(shape,
                         class_set,
                         callbacks,
                         monitor,
                         will_save_h5,
                         preprocess_for_model,
                         after_learned_process)

    @property
    def model(self):
        return self.__model

    def fit(self,
            data: np.ndarray,
            label_set: np.ndarray,
            epochs: int,
            validation_data: Optional[Tuple[np.ndarray, np.ndarray]] = None,
            temp_best_path: str = "",
            save_weights_only: bool = False):
        """
        モデルの適合度を算出する
        :param data: 学習に使うデータ
        :param label_set: 教師ラベル
        :param epochs: エポック数
        :param validation_data: テストに使用するデータ　実データとラベルのセットのタプル
        :param temp_best_path:
        :param save_weights_only:
        :return:
        """
        callbacks = self.get_callbacks(temp_best_path, save_weights_only)
        self.__model = self.run_preprocess_model(self.__model)
        if validation_data is None:
            self.__model.fit(data, label_set, epochs=epochs, callbacks=callbacks)
        else:
            self.__model.fit(data, label_set, epochs=epochs, validation_data=validation_data, callbacks=callbacks)
        self.after_learned_process()
        return self

    def fit_generator(self,
                      image_generator: ImageDataGenerator,
                      data: np.ndarray,
                      label_set: np.ndarray,
                      epochs: int,
                      generator_batch_size: int = 32,
                      validation_data: Optional[Tuple[np.ndarray, np.ndarray]] = None,
                      temp_best_path: str = "",
                      save_weights_only: bool = False):
        """
        モデルの適合度を算出する
        generatorを使ってデータを水増しして学習する場合に使用する
        :param image_generator: keras形式でのデータを水増しするジェネレータ
        :param data: 学習に使うデータ
        :param label_set: 教師ラベル
        :param epochs: エポック数
        :param generator_batch_size: ジェネレータのバッチサイズ
        :param validation_data: テストに使用するデータ　実データとラベルのセットのタプル
        :param temp_best_path:
        :param save_weights_only:
        :return:
        """
        callbacks = self.get_callbacks(temp_best_path, save_weights_only)
        print("fit generator")
        image_generator.fit(data)
        print("start learning")
        self.__model = self.run_preprocess_model(self.__model)
        if validation_data is None:
            self.__history = self.__model.fit(image_generator.flow(data,
                                                                   label_set,
                                                                   batch_size=generator_batch_size),
                                              steps_per_epoch=len(data) / generator_batch_size,
                                              epochs=epochs,
                                              callbacks=callbacks)
        else:
            self.__history = self.__model.fit(image_generator.flow(data,
                                                                   label_set,
                                                                   batch_size=generator_batch_size),
                                              steps_per_epoch=len(data) / generator_batch_size,
                                              epochs=epochs,
                                              validation_data=validation_data,
                                              callbacks=callbacks)
        self.after_learned_process()
        return self

    def predict(self, data: np.ndarray) -> Tuple[np.array, np.array]:
        """
        モデルの適合度から該当するクラスを算出する
        :param data: 算出対象となるデータ
        :return: 判定したインデックスと形式名
        """
        result_set = np.array([np.argmax(result) for result in self.__model.predict(data)])
        class_name_set = np.array([self.__class_set[index] for index in result_set])
        return result_set, class_name_set

    def test(self,
             train_data_set: np.ndarray,
             train_label_set: np.ndarray,
             test_data_set: np.ndarray,
             test_label_set: np.ndarray,
             epochs: int,
             normalize_type: dl.NormalizeType = dl.NormalizeType.Div255,
             image_generator: ImageDataGenerator = None,
             generator_batch_size: int = 32,
             result_dir_name: str = None,
             dir_path: str = None,
             model_name: str = None,
             save_weights_only: bool = False):
        """
        指定したデータセットに対しての正答率を算出する
        :param train_data_set: 学習に使用したデータ
        :param train_label_set: 学習に使用した正解のラベル
        :param test_data_set: テストデータ
        :param test_label_set: テストのラベル
        :param epochs: エポック数
        :param normalize_type: どのように正規化するか
        :param image_generator: keras形式でのデータを水増しするジェネレータ これを引数で渡さない場合はデータの水増しをしない
        :param generator_batch_size: ジェネレータのバッチサイズ
        :param result_dir_name: 記録するためのファイル名のベース
        :param dir_path: 記録するディレクトリ デフォルトではカレントディレクトリ直下にresultディレクトリを作成する
        :param model_name: モデル名　デフォルトではmodel
        :param save_weights_only:
        :return:学習用データの正答率とテスト用データの正答率のタプル
        """
        save_tmp_name = model_name + "_best.h5" if self.will_save_h5 else model_name + "_best"
        if image_generator is None:
            self.fit(train_data_set,
                     train_label_set,
                     epochs,
                     (test_data_set, test_label_set),
                     temp_best_path=save_tmp_name,
                     save_weights_only=save_weights_only)
        else:
            self.fit_generator(image_generator,
                               train_data_set,
                               train_label_set,
                               epochs,
                               generator_batch_size,
                               (test_data_set, test_label_set),
                               temp_best_path=save_tmp_name,
                               save_weights_only=save_weights_only)
        now_result_dir_name = result_dir_name + datetime.now().strftime("%Y%m%d%H%M%S")
        self.record_model(now_result_dir_name, dir_path, model_name)
        self.record_conf_json(now_result_dir_name, dir_path, normalize_type, model_name)
        train_rate = self.calc_succeed_rate(train_data_set, train_label_set)
        test_rate = self.calc_succeed_rate(test_data_set, test_label_set)
        # 教師データと予測されたデータの差が0でなければ誤判定

        return train_rate, test_rate


class ModelForManyData(AbstractModel):
    """
    メモリに乗りきらない量のデータの学習を行う場合はこちらのクラスを使う
    """

    def __init__(self,
                 model_base: keras.engine.training.Model,
                 class_set: List[str],
                 callbacks: Optional[List[keras.callbacks.Callback]] = None,
                 monitor: str = "",
                 will_save_h5: bool = True,
                 preprocess_for_model: ModelPreProcessor = None,
                 after_learned_process: Optional[Callable[[None], None]] = None):
        """

        :param model_base: kerasで構築したモデル
        :param class_set: クラスの元となったリスト
        :param callbacks: モデルに渡すコールバック関数
        :param monitor: モデルの途中で記録するパラメータ　デフォルトだと途中で記録しない
        :param will_save_h5: 途中モデル読み込み時に旧式のh5ファイルで保存するかどうか　デフォルトだと保存する
        :param preprocess_for_model: モデル学習前にモデルに対してする処理
        :param after_learned_process: モデル学習後の後始末
        """
        self.__model = model_base
        self.__model = model_base
        shape = model_base.input[0].shape.as_list() if type(model_base.input) is list else model_base.input.shape.as_list()
        super().__init__(shape,
                         class_set,
                         callbacks,
                         monitor,
                         will_save_h5,
                         preprocess_for_model,
                         after_learned_process)

    @property
    def callbacks_metric(self):
        out_labels = self.model.metrics_names
        return ['val_' + n for n in out_labels]

    @property
    def base_logger(self):
        print(type(self.__model))
        return BaseLogger(stateful_metrics=self.__model.stateful_metric_names)

    @property
    def progbar_logger(self):
        return ProgbarLogger(count_mode='steps', stateful_metrics=self.model.stateful_metric_names)

    def get_callbacks_for_multi_input(self, temp_best_path, save_weights_only= False):
        base_callbacks = self.get_callbacks(temp_best_path, save_weights_only)
        if base_callbacks is None or base_callbacks == []:
            return [self.model.history]
        return base_callbacks + [self.model.history]

    def build_callbacks_for_multi_input(self,
                                        epochs: int,
                                        temp_best_path,
                                        steps_per_epoch: Optional[int] = None,
                                        validation_data: Union[Optional[Tuple[np.ndarray, np.ndarray]],
                                                               DataLoaderFromPathsWithDataAugmentation,
                                                               DataLoaderFromPaths] = None,
                                        save_weights_only=False):
        """
        一つのデータから複数の入力を使用する場合のコールバックを生成する
        :param epochs: エポック数
        :param temp_best_path:
        :param steps_per_epoch:
        :param validation_data
        :param save_weights_only:
        :return:
        """
        self.__model.history = History()
        build_callbacks = [self.base_logger, self.progbar_logger]
        raw_callbacks = build_callbacks + self.get_callbacks_for_multi_input(temp_best_path, save_weights_only)
        callbacks = CallbackList(raw_callbacks)
        callbacks.set_model(self.model)
        will_validate =  bool(validation_data)
        callbacks.set_params({
            'epochs': epochs,
            'steps': steps_per_epoch,
            'verbose': 1,
            'do_validation': will_validate,
            'metrics': self.callbacks_metric,
        })
        return callbacks, will_validate

    @property
    def model(self):
        return self.__model

    def fit_generator(self,
                      image_generator: Union[DataLoaderFromPathsWithDataAugmentation, DataLoaderFromPaths],
                      epochs: int,
                      validation_data: Union[Optional[Tuple[np.ndarray, np.ndarray]],
                                             DataLoaderFromPathsWithDataAugmentation,
                                             DataLoaderFromPaths] = None,
                      steps_per_epoch: Optional[int] = None,
                      validation_steps: Optional[int] = None,
                      temp_best_path: str = "",
                      save_weights_only: bool = False,
                      will_use_multi_inputs_per_one_image: bool = False):
        """
        モデルの適合度を算出する
        :param image_generator: ファイルパスから学習データを生成する生成器
        :param epochs: エポック数
        :param validation_data: テストに使用するデータ　実データとラベルのセットのタプル
        :param steps_per_epoch:
        :param validation_steps:
        :param temp_best_path:
        :param save_weights_only:
        :param will_use_multi_inputs_per_one_image:
        :return:
        """
        print("fit generator")
        self.__model = self.run_preprocess_model(self.__model)
        if validation_data is None:
            if will_use_multi_inputs_per_one_image:
                self.fit_generator_for_multi_inputs_per_one_image(image_generator,
                                                                  epochs=epochs,
                                                                  steps_per_epoch=steps_per_epoch,
                                                                  temp_best_path=temp_best_path,
                                                                  save_weights_only=save_weights_only)
                return self
            callbacks = self.get_callbacks(temp_best_path, save_weights_only)
            self.__history = self.__model.fit(image_generator,
                                              steps_per_epoch=steps_per_epoch,
                                              epochs=epochs,
                                              callbacks=callbacks)
        else:
            if will_use_multi_inputs_per_one_image:
                if will_use_multi_inputs_per_one_image:
                    self.fit_generator_for_multi_inputs_per_one_image(image_generator,
                                                                      steps_per_epoch=steps_per_epoch,
                                                                      validation_steps=validation_steps,
                                                                      epochs=epochs,
                                                                      validation_data=validation_data,
                                                                      temp_best_path=temp_best_path,
                                                                      save_weights_only=save_weights_only)
                    return self
            print('epochs', epochs)
            callbacks = self.get_callbacks(temp_best_path, save_weights_only)
            self.__history = self.__model.fit(image_generator,
                                              steps_per_epoch=steps_per_epoch,
                                              validation_steps=validation_steps,
                                              epochs=epochs,
                                              validation_data=validation_data,
                                              callbacks=callbacks)
        self.after_learned_process()
        return self

    def test(self,
             image_generator: Union[DataLoaderFromPathsWithDataAugmentation, DataLoaderFromPaths],
             epochs: int,
             validation_data: Union[Optional[Tuple[np.ndarray, np.ndarray]],
                                    DataLoaderFromPathsWithDataAugmentation,
                                    DataLoaderFromPaths] = None,
             normalize_type: dl.NormalizeType = dl.NormalizeType.Div255,
             result_dir_name: str = None,
             dir_path: str = None,
             model_name: str = None,
             steps_per_epoch: Optional[int] = None,
             validation_steps: Optional[int] = None,
             save_weights_only: bool = False,
             will_use_multi_inputs_per_one_image: bool = False
             ):
        """
        指定したデータセットに対しての正答率を算出する
        :param image_generator: ファイルパスから学習データを生成する生成器
        :param epochs: エポック数
        :param validation_data: テストに使用するデータ　実データとラベルのセットのタプルもしくはimage_generatorと同じ形式
        :param epochs: エポック数
        :param normalize_type: どのように正規化するか
        :param result_dir_name: 記録するためのファイル名のベース
        :param dir_path: 記録するディレクトリ デフォルトではカレントディレクトリ直下にresultディレクトリを作成する
        :param model_name: モデル名　デフォルトではmodel
        :param steps_per_epoch: 記録後モデルを削除するかどうか
        :param validation_steps: 記録後モデルを削除するかどうか
        :param save_weights_only:
        :param will_use_multi_inputs_per_one_image:
        :return:
        """
        write_dir_path = build_record_path(result_dir_name, dir_path)
        save_tmp_name = model_name + "_best.h5" if self.will_save_h5 else model_name + "_best"
        self.fit_generator(image_generator,
                           epochs,
                           validation_data,
                           steps_per_epoch=steps_per_epoch,
                           validation_steps=validation_steps,
                           temp_best_path=os.path.join(write_dir_path, save_tmp_name),
                           save_weights_only=save_weights_only,
                           will_use_multi_inputs_per_one_image=will_use_multi_inputs_per_one_image)
        self.record_model(result_dir_name, dir_path, model_name)
        self.record_conf_json(result_dir_name, dir_path, normalize_type, model_name)

    def fit_generator_for_multi_inputs_per_one_image(self,
                                                     image_generator: Union[DataLoaderFromPathsWithDataAugmentation, DataLoaderFromPaths],
                                                     epochs: int,
                                                     validation_data: Union[Optional[Tuple[np.ndarray, np.ndarray]],
                                                                            DataLoaderFromPathsWithDataAugmentation,
                                                                            DataLoaderFromPaths] = None,
                                                     steps_per_epoch: Optional[int] = None,
                                                     validation_steps: Optional[int] = None,
                                                     temp_best_path: str = "",
                                                     save_weights_only: bool = False,
                                                     wait_time: float = 0.01):
        callbacks, will_validate = self.build_callbacks_for_multi_input(epochs,
                                                                        temp_best_path,
                                                                        steps_per_epoch,
                                                                        validation_data,
                                                                        save_weights_only)
        try:
            if will_validate:
                val_data = validation_data
                val_enqueuer = GeneratorEnqueuer(
                    val_data,
                    use_multiprocessing=False)
                val_enqueuer.start(workers=1,
                                   max_queue_size=10)
                val_enqueuer_gen = val_enqueuer.get()
            enqueuer = GeneratorEnqueuer(
                    image_generator,
                    use_multiprocessing=False,
                    wait_time=wait_time)
            enqueuer.start(workers=1, max_queue_size=10)
            output_generator = enqueuer.get()

            self.__model.stop_training = False
            # Construct epoch logs.
            epoch_logs = {}
            epoch = 0
            while epoch < epochs:
                for m in self.model.stateful_metric_functions:
                    m.reset_states()
                callbacks.on_epoch_begin(epoch)
                steps_done = 0
                batch_index = 0
            while steps_done < steps_per_epoch:
                generator_output = next(output_generator)
                if not hasattr(generator_output, '__len__'):
                    raise ValueError('Output of generator should be '
                                     'a tuple `(x, y, sample_weight)` '
                                     'or `(x, y)`. Found: ' +
                                     str(generator_output))

                if len(generator_output) == 2:
                    x, y = generator_output
                    sample_weight = None
                elif len(generator_output) == 3:
                    x, y, sample_weight = generator_output
                else:
                    raise ValueError('Output of generator should be '
                                     'a tuple `(x, y, sample_weight)` '
                                     'or `(x, y)`. Found: ' +
                                     str(generator_output))
                batch_logs = {}
                if x is None or len(x) == 0:
                    # Handle data tensors support when no input given
                    # step-size = 1 for data tensors
                    batch_size = 1
                elif isinstance(x, list):
                    batch_size = x[0].shape[0]
                elif isinstance(x, dict):
                    batch_size = list(x.values())[0].shape[0]
                else:
                    batch_size = x.shape[0]
                batch_logs['batch'] = batch_index
                batch_logs['size'] = batch_size
                callbacks.on_batch_begin(batch_index, batch_logs)

                outs = self.__model.train_on_batch(x,
                                                   y,
                                                   sample_weight=sample_weight,
                                                   class_weight=None)

                outs = to_list(outs)
                for l, o in zip(self.model.metrics_names, outs):
                    batch_logs[l] = o

                callbacks.on_batch_end(batch_index, batch_logs)

                batch_index += 1
                steps_done += 1

                # Epoch finished.
                if steps_done >= steps_per_epoch and will_validate:
                    val_outs = self.model.evaluate_generator(
                            val_enqueuer_gen,
                            validation_steps,
                            workers=0)
                    val_outs = to_list(val_outs)
                    # Same labels assumed.
                    for l, o in zip(self.model.metrics_names, val_outs):
                        epoch_logs['val_' + l] = o

                if self.model.metrics_names.stop_training:
                    break

                callbacks.on_epoch_end(epoch, epoch_logs)
                epoch += 1
                if self.model.metrics_names.stop_training:
                    break

        finally:
            try:
                if enqueuer is not None:
                    enqueuer.stop()
            finally:
                if val_enqueuer is not None:
                    val_enqueuer.stop()

        callbacks.on_train_end()
        return self.model.history


