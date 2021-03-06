# Copyright 2021, Maxime Burchi.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# PyTorch
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch._VF as _VF

# Initializations
from nnet.initializations import init_dict

# Module
from nnet.module import Module

###############################################################################
# Layers
###############################################################################

class SwitchLinear(nn.Module):

    def __init__(self, num_experts, in_features, out_features, bias=True, device=None, dtype=None):
        super(SwitchLinear, self).__init__()

        # params
        self.num_experts = num_experts

        # Experts
        self.experts = nn.ModuleList([nn.Linear(
            in_features=in_features,
            out_features=out_features,
            bias=bias,
            device=device,
            dtype=dtype
        ) for _ in range(self.num_experts)])

    def forward(self, x, indices):

        # Create Weight (N, Di, Do)
        weight = [self.experts[index].weight for index in indices]
        weight = torch.stack(weight, dim=0)

        # Create Bias (N, Do)
        bias = [self.experts[index].bias for index in indices]
        bias = torch.stack(bias, dim=0)

        # Unsqueeze Input (N, 1, Di)
        x = x.unsqueeze(dim=1)

        # Compute Output (N, 1, Do)
        x = x.matmul(weight.transpose(1, 2))

        # Squeeze Output (N, Do)
        x = x.squeeze(dim=1)

        # Add Bias
        x = x + bias

        return x

class Linear(nn.Linear):

    def __init__(self, in_features, out_features, bias=True, device=None, dtype=None):
        super(Linear, self).__init__(in_features=in_features, out_features=out_features, bias=bias, device=device, dtype=dtype)

        # Variational Noise
        self.noise = None
        self.vn_std = None

    def init_vn(self, vn_std):

        # Variational Noise
        self.vn_std = vn_std

    def sample_synaptic_noise(self, distributed):

        # Sample Noise
        self.noise = torch.normal(mean=0.0, std=1.0, size=self.weight.size(), device=self.weight.device, dtype=self.weight.dtype)

        # Broadcast Noise
        if distributed:
            torch.distributed.broadcast(self.noise, 0)

    def forward(self, x):

        # Weight
        weight = self.weight

        # Add Noise
        if self.noise is not None and self.training:
            weight = weight + self.vn_std * self.noise
            
        # Apply Weight
        x = F.linear(x, weight, self.bias)

        return x

class Conv1d(nn.Conv1d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1, 
        dilation=1, 
        groups=1, 
        bias=True,
        padding_mode='zeros',
        device=None, 
        dtype=None,

        padding="same", 
        channels_last=False
    ):
        super(Conv1d, self).__init__(
            in_channels=in_channels, 
            out_channels=out_channels, 
            kernel_size=kernel_size, 
            stride=stride, 
            padding=0, 
            dilation=dilation, 
            groups=groups, 
            bias=bias, 
            padding_mode=padding_mode,
            device=device,
            dtype=dtype
        )

        # Assert
        assert padding in ["valid", "same", "causal"]

        # Padding
        if padding == "valid":
            self.pre_padding = nn.Identity()
        elif padding == "same":
            self.pre_padding = nn.ConstantPad1d(padding=(self.kernel_size[0] // 2, (self.kernel_size[0] - 1) // 2), value=0)
        elif padding == "causal":
            self.pre_padding = nn.ConstantPad1d(padding=(self.kernel_size[0] - 1, 0), value=0)

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 2, 1))
            self.output_permute = Permute(dims=(0, 2, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        # Padding
        x = self.pre_padding(self.input_permute(x))

        # Apply Weight
        x = self.output_permute(super(Conv1d, self).forward(x))

        return x

class Conv2d(nn.Conv2d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1,
        dilation=1, 
        groups=1, 
        bias=True, 
        padding_mode='zeros',
        device=None, 
        dtype=None,

        padding="same", 
        channels_last=False
    ):
        
        super(Conv2d, self).__init__(
            in_channels=in_channels, 
            out_channels=out_channels, 
            kernel_size=kernel_size, 
            stride=stride, 
            padding=0, 
            dilation=dilation, 
            groups=groups, 
            bias=bias,
            padding_mode=padding_mode,
            device=device,
            dtype=dtype
        )

        # Assert
        assert padding in ["valid", "same"]

        # Padding
        if padding == "valid":

            self.pre_padding = nn.Identity()

        elif padding == "same":

            self.pre_padding = nn.ConstantPad2d(
                padding=(
                    self.kernel_size[1] // 2,
                    (self.kernel_size[1] - 1) // 2, 
                    self.kernel_size[0] // 2,
                    (self.kernel_size[0] - 1) // 2 
                ), 
                value=0
            )

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 3, 1, 2))
            self.output_permute = Permute(dims=(0, 2, 3, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        # Padding
        x = self.pre_padding(self.input_permute(x))

        # Apply Weight
        x = self.output_permute(super(Conv2d, self).forward(x))

        return x

class Conv3d(nn.Conv3d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1, 
        dilation=1, 
        groups=1, 
        bias=True,
        padding_mode='zeros',
        device=None, 
        dtype=None,

        padding="same", 
        channels_last=False
    ):

        super(Conv3d, self).__init__(
            in_channels=in_channels, 
            out_channels=out_channels, 
            kernel_size=kernel_size, 
            stride=stride, 
            padding=0, 
            dilation=dilation, 
            groups=groups, 
            bias=bias,
            padding_mode=padding_mode,
            device=device,
            dtype=dtype
        )

        # Assert
        assert padding in ["valid", "same", "causal"]

        # Padding
        if padding == "valid":

            self.pre_padding = nn.Identity()

        elif padding == "same":

            self.pre_padding = nn.ConstantPad3d(
                padding=(
                    self.kernel_size[2] // 2,
                    (self.kernel_size[2] - 1) // 2, 
                    self.kernel_size[1] // 2,
                    (self.kernel_size[1] - 1) // 2, 
                    self.kernel_size[0] // 2,
                    (self.kernel_size[0] - 1) // 2 
                ), 
                value=0
            )

        elif padding == "causal":

            self.pre_padding = nn.ConstantPad3d(
                padding=(
                    self.kernel_size[2] // 2,
                    (self.kernel_size[2] - 1) // 2, 
                    self.kernel_size[1] // 2,
                    (self.kernel_size[1] - 1) // 2, 
                    self.kernel_size[0] - 1,
                    0
                ), 
                value=0
            )

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 4, 1, 2, 3))
            self.output_permute = Permute(dims=(0, 2, 3, 4, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        # Padding
        x = self.pre_padding(self.input_permute(x))

        # Apply Weight
        x = self.output_permute(super(Conv3d, self).forward(x))

        return x

class ConvTranspose1d(nn.ConvTranspose1d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1,
        output_padding=0, 
        groups=1, 
        bias=True, 
        dilation=1,
        padding_mode='zeros',
        device=None, 
        dtype=None,

        padding="same",
        channels_last=False
    ):

        super(ConvTranspose1d, self).__init__(
                in_channels=in_channels, 
                out_channels=out_channels, 
                kernel_size=kernel_size, 
                stride=stride, 
                padding=0,
                output_padding=output_padding, 
                groups=groups, 
                bias=bias,
                dilation=dilation,
                padding_mode=padding_mode,
                device=device,
                dtype=dtype
            )

        # Default to no Input Padding
        for i in range(len(self.padding)):
            self.padding[i] = self.dilation[i] * (self.kernel_size[i] - 1)

        # Assert
        assert padding in ["valid", "same", "causal"]

        # Padding
        if padding == "valid":
            self.pre_padding = nn.ConstantPad1d(padding=(self.dilation[0] * (self.kernel_size[0] - 1), self.dilation[0] * (self.kernel_size[0] - 1)), value=0)
        elif padding == "same":
            self.pre_padding = nn.ConstantPad1d(padding=(self.kernel_size[0] // 2, (self.kernel_size[0] - 1) // 2), value=0)
        elif padding == "causal":
            self.pre_padding = nn.ConstantPad1d(padding=(self.kernel_size[0] - 1, 0), value=0)

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 2, 1))
            self.output_permute = Permute(dims=(0, 2, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        # Padding
        x = self.pre_padding(self.input_permute(x))

        # Apply Weight
        x = self.output_permute(super(ConvTranspose1d, self).forward(x))

        return x

class ConvTranspose2d(nn.ConvTranspose2d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1,
        padding=0,
        output_padding=0, 
        groups=1, 
        bias=True, 
        dilation=1,
        padding_mode='zeros',
        device=None, 
        dtype=None,

        channels_last=False
    ):

        super(ConvTranspose2d, self).__init__(
            in_channels=in_channels, 
            out_channels=out_channels, 
            kernel_size=kernel_size, 
            stride=stride, 
            padding=padding,
            output_padding=output_padding, 
            groups=groups, 
            bias=bias,
            dilation=dilation,
            padding_mode=padding_mode,
            device=device,
            dtype=dtype
        )

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 3, 1, 2))
            self.output_permute = Permute(dims=(0, 2, 3, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        # Apply Weight
        x = self.output_permute(super(ConvTranspose2d, self).forward(self.input_permute(x)))

        return x

class ConvTranspose3d(nn.ConvTranspose3d):

    def __init__(
        self, 
        in_channels, 
        out_channels, 
        kernel_size, 
        stride=1,
        padding=0,
        output_padding=0, 
        groups=1, 
        bias=True, 
        dilation=1,
        padding_mode='zeros',
        device=None, 
        dtype=None,

        channels_last=False
    ):

        super(ConvTranspose3d, self).__init__(
            in_channels=in_channels, 
            out_channels=out_channels, 
            kernel_size=kernel_size, 
            stride=stride, 
            padding=padding,
            output_padding=min(output_padding, stride-1), 
            groups=groups, 
            bias=bias,
            dilation=dilation,
            padding_mode=padding_mode,
            device=device,
            dtype=dtype
        )

        # Channels Last
        if channels_last:
            self.input_permute = Permute(dims=(0, 4, 1, 2, 3))
            self.output_permute = Permute(dims=(0, 2, 3, 4, 1))
        else:
            self.input_permute = nn.Identity()
            self.output_permute = nn.Identity()

    def forward(self, x):

        return self.output_permute(super(ConvTranspose3d, self).forward(self.input_permute(x)))

class LSTM(nn.LSTM):

    def __init__(self, input_size, hidden_size, num_layers, batch_first, bidirectional):
        super(LSTM, self).__init__(
            input_size=input_size, 
            hidden_size=hidden_size, 
            num_layers=num_layers,
            batch_first=batch_first, 
            bidirectional=bidirectional)

        # Variational Noise
        self.noises = None
        self.vn_std = None

    def init_vn(self, vn_std):

        # Variational Noise
        self.vn_std = vn_std

    def sample_synaptic_noise(self, distributed):

        # Sample Noise
        self.noises = []
        for i in range(0, len(self._flat_weights), 4):
            self.noises.append(torch.normal(mean=0.0, std=1.0, size=self._flat_weights[i].size(), device=self._flat_weights[i].device, dtype=self._flat_weights[i].dtype))
            self.noises.append(torch.normal(mean=0.0, std=1.0, size=self._flat_weights[i+1].size(), device=self._flat_weights[i+1].device, dtype=self._flat_weights[i+1].dtype))

        # Broadcast Noise
        if distributed:
            for noise in self.noises:
                torch.distributed.broadcast(noise, 0)

    def forward(self, input, hx=None):  # noqa: F811

        orig_input = input
        # xxx: isinstance check needs to be in conditional for TorchScript to compile
        if isinstance(orig_input, nn.utils.rnn.PackedSequence):
            input, batch_sizes, sorted_indices, unsorted_indices = input
            max_batch_size = batch_sizes[0]
            max_batch_size = int(max_batch_size)
        else:
            batch_sizes = None
            max_batch_size = input.size(0) if self.batch_first else input.size(1)
            sorted_indices = None
            unsorted_indices = None

        if hx is None:
            num_directions = 2 if self.bidirectional else 1
            zeros = torch.zeros(self.num_layers * num_directions,
                                max_batch_size, self.hidden_size,
                                dtype=input.dtype, device=input.device)
            hx = (zeros, zeros)
        else:
            # Each batch of the hidden state should match the input sequence that
            # the user believes he/she is passing in.
            hx = self.permute_hidden(hx, sorted_indices)

        # Add Noise
        if self.noises is not None and self.training:
            weight = []
            for i in range(0, len(self.noises), 2):
                weight.append(self._flat_weights[2*i] + self.vn_std * self.noises[i])
                weight.append(self._flat_weights[2*i+1] + self.vn_std * self.noises[i+1])
                weight.append(self._flat_weights[2*i+2])
                weight.append(self._flat_weights[2*i+3])
        else:
            weight = self._flat_weights

        self.check_forward_args(input, hx, batch_sizes)
        if batch_sizes is None:
            result = _VF.lstm(input, hx, weight, self.bias, self.num_layers,
                              self.dropout, self.training, self.bidirectional, self.batch_first)
        else:
            result = _VF.lstm(input, batch_sizes, hx, weight, self.bias,
                              self.num_layers, self.dropout, self.training, self.bidirectional)
        output = result[0]
        hidden = result[1:]
        # xxx: isinstance check needs to be in conditional for TorchScript to compile
        if isinstance(orig_input, nn.utils.rnn.PackedSequence):
            output_packed = nn.utils.rnn.PackedSequence(output, batch_sizes, sorted_indices, unsorted_indices)
            return output_packed, self.permute_hidden(hidden, unsorted_indices)
        else:
            return output, self.permute_hidden(hidden, unsorted_indices)


class Embedding(nn.Embedding): 

    def __init__(self, num_embeddings, embedding_dim, padding_idx = None):
        super(Embedding, self).__init__(
            num_embeddings=num_embeddings,
            embedding_dim=embedding_dim,
            padding_idx=padding_idx)

        # Variational Noise
        self.noise = None
        self.vn_std = None

    def init_vn(self, vn_std):

        # Variational Noise
        self.vn_std = vn_std

    def sample_synaptic_noise(self, distributed):

        # Sample Noise
        self.noise = torch.normal(mean=0.0, std=1.0, size=self.weight.size(), device=self.weight.device, dtype=self.weight.dtype)

        # Broadcast Noise
        if distributed:
            torch.distributed.broadcast(self.noise, 0)

    def forward(self, input):

        # Weight
        weight = self.weight

        # Add Noise
        if self.noise is not None and self.training:
            weight = weight + self.vn_std * self.noise

        # Apply Weight
        return F.embedding(input, weight, self.padding_idx, self.max_norm, self.norm_type, self.scale_grad_by_freq, self.sparse)

###############################################################################
# Regularization Layers
###############################################################################

class Dropout(nn.Dropout):

    def __init__(self, p=0.5, inplace=False):
        super(Dropout, self).__init__(p, inplace)

    def forward(self, x):

        return super(Dropout, self).forward(x)

###############################################################################
# Tensor Manipulation Layers
###############################################################################

class Upsample3d(nn.Upsample):

    def __init__(self, scale_factor):

        # Assert
        if isinstance(scale_factor, int):
            scale_factor = (scale_factor, scale_factor, scale_factor)
        else:
            assert isinstance(scale_factor, list) or isinstance(scale_factor, tuple)
            assert len(scale_factor) == 3

        # Init
        super(Upsample3d, self).__init__(scale_factor=scale_factor)

class Flatten(nn.Flatten):

    def __init__(self, *args, **kargs):
        super(Flatten, self).__init__(*args, **kargs)

    def forward(self, x):

        return super(Flatten, self).forward(x)

class Transpose(nn.Module):

    def __init__(self, dim0, dim1):
        super(Transpose, self).__init__()
        self.dim0 = dim0
        self.dim1 = dim1

    def forward(self, x):

        return x.transpose(self.dim0, self.dim1)

class Permute(nn.Module):

    def __init__(self, dims):
        super(Permute, self).__init__()
        self.dims = dims

    def forward(self, x):

        return x.permute(self.dims)

class Reshape(nn.Module):

    def __init__(self, shape, include_batch=True):
        super(Reshape, self).__init__()
        self.shape = tuple(shape)
        self.include_batch = include_batch

    def forward(self, x):

        if self.include_batch:
            return x.reshape(self.shape)
        else:
            return x.reshape(x.size()[0:1] + self.shape)

class Unsqueeze(nn.Module):

    def __init__(self, dim):
        super(Unsqueeze, self).__init__()
        self.dim = dim

    def forward(self, x):

        return x.unsqueeze(dim=self.dim)

class GlobalAvgPool1d(nn.Module):

    def __init__(self, dim=1, keepdim=False):
        super(GlobalAvgPool1d, self).__init__()
        self.dim = dim
        self.keepdim = keepdim

    def forward(self, x, mask=None):

        if mask != None:
            x = (x * mask).sum(dim=self.dim, keepdim=self.keepdim) / mask.count_nonzero(dim=self.dim)
        else:
            x = x.mean(dim=self.dim, keepdim=self.keepdim)

        return x

class GlobalAvgPool2d(nn.Module):

    def __init__(self, dim=(2, 3), keepdim=False):
        super(GlobalAvgPool2d, self).__init__()
        self.dim = dim
        self.keepdim = keepdim

    def forward(self, x, mask=None):

        if mask != None:
            x = (x * mask).sum(dim=self.dim, keepdim=self.keepdim) / mask.count_nonzero(dim=self.dim)
        else:
            x = x.mean(dim=self.dim, keepdim=self.keepdim)

        return x

class GlobalMaxPool2d(nn.Module):

    def __init__(self, dim=(2, 3), keepdim=False):
        super(GlobalMaxPool2d, self).__init__()
        self.dim = dim
        self.keepdim = keepdim

    def forward(self, x, output_dict=False):

        x = x.amax(dim=self.dim, keepdim=self.keepdim)

        return x

class GlobalAvgPool3d(nn.Module):

    def __init__(self, axis=(2, 3, 4)):
        super(GlobalAvgPool3d, self).__init__()
        self.axis = axis

    def forward(self, x, mask=None):

        return x.mean(axis=self.axis)

###############################################################################
# Layer Dictionary
###############################################################################

layer_dict = {
    "Linear": Linear,

    "Conv1d": Conv1d,
    "Conv2d": Conv2d,
    "Conv3d": Conv3d,

    "ConvTranspose1d": ConvTranspose1d,
    "ConvTranspose2d": ConvTranspose2d,
    "ConvTranspose3d": ConvTranspose3d,

    "MaxPool1d": nn.MaxPool1d,
    "MaxPool2d": nn.MaxPool2d,
    "MaxPool3d": nn.MaxPool3d,

    "Dropout": Dropout,

    "Flatten": Flatten,
    "Transpose": Transpose,
    "Permute": Permute,
    "Reshape": Reshape,
    "Unsqueeze": Unsqueeze,
    "GlobalAvgPool1d": GlobalAvgPool1d,
    "GlobalAvgPool2d": GlobalAvgPool2d,
    "GlobalAvgPool3d": GlobalAvgPool3d,
    "GlobalMaxPool2d": GlobalMaxPool2d
}