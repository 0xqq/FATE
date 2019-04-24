#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from arch.api.model_manager import manager as model_manager
from arch.api.proto import feature_binning_meta_pb2, feature_binning_param_pb2
from arch.api.utils import log_utils
from federatedml.feature.binning import IVAttributes
from federatedml.feature.binning import QuantileBinning
from federatedml.statistic.data_overview import get_header
from federatedml.util import abnormal_detection
from federatedml.util import consts
from federatedml.util.transfer_variable import HeteroFeatureBinningTransferVariable

LOGGER = log_utils.getLogger()


class BaseHeteroFeatureBinning(object):
    def __init__(self, params):
        self.bin_param = params
        if self.bin_param.method == consts.QUANTILE:
            self.binning_obj = QuantileBinning(self.bin_param)
        else:

            self.binning_obj = QuantileBinning(self.bin_param)
        self.transfer_variable = HeteroFeatureBinningTransferVariable()
        self.cols = params.cols
        self.cols_dict = {}

        self.header = []
        self.has_synchronized = False
        self.flowid = ''
        self.iv_attrs = None

    def _save_meta(self, name, namespace):
        meta_protobuf_obj = feature_binning_meta_pb2.FeatureBinningMeta(
            method=self.bin_param.method,
            compress_thres=self.bin_param.compress_thres,
            head_size=self.bin_param.head_size,
            error=self.bin_param.error,
            bin_num=self.bin_param.bin_num,
            cols=self.cols,
            adjustment_factor=self.bin_param.adjustment_factor,
            local_only=self.bin_param.local_only)
        buffer_type = "HeteroFeatureBinningGuest.meta"

        model_manager.save_model(buffer_type=buffer_type,
                                 proto_buffer=meta_protobuf_obj,
                                 name=name,
                                 namespace=namespace)
        return buffer_type

    def save_model(self, name, namespace):
        meta_buffer_type = self._save_meta(name, namespace)

        iv_attrs = {}
        for col_name, iv_attr in self.iv_attrs.items():
            LOGGER.debug("{}th iv attr: {}".format(col_name, iv_attr.__dict__))
            iv_result = iv_attr.result_dict()
            iv_object = feature_binning_param_pb2.IVParam(**iv_result)

            iv_attrs[col_name] = iv_object

        # host_iv_attrs = []
        # if self.host_iv_attrs is not None:
        #     for idx, iv_attr in enumerate(self.host_iv_attrs):
        #         iv_result = iv_attr.result_dict()
        #         iv_object = feature_binning_param_pb2.IVParam(**iv_result)
        #
        #         host_iv_attrs.append(iv_object)

        result_obj = feature_binning_param_pb2.FeatureBinningParam(iv_result=iv_attrs)

        param_buffer_type = "HeteroFeatureBinningGuest.param"

        model_manager.save_model(buffer_type=param_buffer_type,
                                 proto_buffer=result_obj,
                                 name=name,
                                 namespace=namespace)

        return [(meta_buffer_type, param_buffer_type)]

    def load_model(self, name, namespace):

        result_obj = feature_binning_param_pb2.FeatureBinningParam()
        model_manager.read_model(buffer_type="HeteroFeatureBinningGuest.param",
                                 proto_buffer=result_obj,
                                 name=name,
                                 namespace=namespace)
        iv_attrs = dict(result_obj.iv_result)
        self.iv_attrs = {}
        self.cols = []
        for col_name, iv_attr_obj in iv_attrs.items():
            iv_attr = IVAttributes([], [], [], [], [], [])
            iv_attr.reconstruct(iv_attr_obj)
            self.iv_attrs[col_name] = iv_attr
            self.cols.append(col_name)

    def set_flowid(self, flowid="samole"):
        self.flowid = flowid
        self.transfer_variable.set_flowid(self.flowid)

    def reset(self, params, flowid):
        self.bin_param = params
        if self.bin_param.method == consts.QUANTILE:
            self.binning_obj = QuantileBinning(self.bin_param)
        else:

            self.binning_obj = QuantileBinning(self.bin_param)
        self.cols = params.cols

        # self.flowid += flowid_postfix
        self.set_flowid(flowid)

    def _parse_cols(self, data_instances):
        header = get_header(data_instances)
        self.header = header
        LOGGER.debug("data_instance count: {}, header: {}".format(data_instances.count(), header))
        if self.cols == -1:
            if header is None:
                raise RuntimeError('Cannot get feature header, please check input data')
            self.cols = header
        self.cols_dict = {}
        for col in self.cols:
            col_index = header.index(col)
            self.cols_dict[col] = col_index

    def set_schema(self, data_instance):
        data_instance.schema = {"header": self.header}

    def _abnormal_detection(self, data_instances):
        """
        Make sure input data_instances is valid.
        """
        abnormal_detection.empty_table_detection(data_instances)
        abnormal_detection.empty_feature_detection(data_instances)
