from typing import Dict, List, Optional, Any

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


class TemporalBlock(nn.Module):
    def __init__(self, n_inputs: int, n_outputs: int, kernel_size: int, stride: int, dilation: int, padding: int, dropout: float = 0.2):
        super().__init__()
        self.conv1 = nn.Conv1d(n_inputs, n_outputs, kernel_size, stride=stride, padding=padding, dilation=dilation)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout)
        self.conv2 = nn.Conv1d(n_outputs, n_outputs, kernel_size, stride=stride, padding=padding, dilation=dilation)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(dropout)
        self.net = nn.Sequential(self.conv1, self.relu1, self.dropout1, self.conv2, self.relu2, self.dropout2)
        self.downsample = nn.Conv1d(n_inputs, n_outputs, 1) if n_inputs != n_outputs else None
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)


class TemporalConvNet(nn.Module):
    def __init__(self, num_inputs: int, num_channels: List[int], kernel_size: int = 2, dropout: float = 0.2):
        super().__init__()
        layers = []
        num_levels = len(num_channels)
        for i in range(num_levels):
            dilation_size = 2 ** i
            in_channels = num_inputs if i == 0 else num_channels[i - 1]
            out_channels = num_channels[i]
            padding = (kernel_size - 1) * dilation_size
            layers.append(TemporalBlock(in_channels, out_channels, kernel_size, stride=1, dilation=dilation_size, padding=padding, dropout=dropout))
        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


class CarbonForecaster:
    """Trainable TCN-based carbon intensity forecaster."""

    def __init__(
        self,
        horizon_hours: int = 4,
        seq_len: int = 12,
        num_channels: Optional[List[int]] = None,
        kernel_size: int = 3,
        dropout: float = 0.1,
        device: str = "cpu",
    ):
        self.horizon_hours = horizon_hours
        self.seq_len = seq_len
        self.device = torch.device(device)
        self.num_channels = num_channels or [16, 32]
        self.network = TemporalConvNet(1, self.num_channels, kernel_size=kernel_size, dropout=dropout).to(self.device)
        self.projection = nn.Linear(self.num_channels[-1], horizon_hours).to(self.device)
        self.loss_fn = nn.MSELoss()
        self.optimizer = optim.Adam(list(self.network.parameters()) + list(self.projection.parameters()), lr=1e-3)
        self.trained = False

    def _build_dataset(self, history: List[float]) -> Optional[tuple]:
        data = np.array(history, dtype=np.float32)
        if len(data) < self.seq_len + self.horizon_hours:
            return None

        x, y = [], []
        for start in range(0, len(data) - self.seq_len - self.horizon_hours + 1):
            x.append(data[start : start + self.seq_len])
            y.append(data[start + self.seq_len : start + self.seq_len + self.horizon_hours])

        x_tensor = torch.tensor(np.stack(x), dtype=torch.float32, device=self.device).unsqueeze(1)
        y_tensor = torch.tensor(np.stack(y), dtype=torch.float32, device=self.device)
        return x_tensor, y_tensor

    def train(self, history: List[float], epochs: int = 20) -> None:
        dataset = self._build_dataset(history)
        if dataset is None:
            return

        x_tensor, y_tensor = dataset
        self.network.train()
        for _ in range(epochs):
            self.optimizer.zero_grad()
            output = self.network(x_tensor)
            last_step = output[:, :, -1]
            predictions = self.projection(last_step)
            loss = self.loss_fn(predictions, y_tensor)
            loss.backward()
            self.optimizer.step()

        self.trained = True

    def forecast(self, history: List[float], watttime_forecast: Optional[List[Dict[str, Any]]] = None) -> Dict[int, float]:
        # If WattTime forecast data is available, use it as primary source
        if watttime_forecast and len(watttime_forecast) > 0:
            forecast_dict = {}
            for i, point in enumerate(watttime_forecast[:self.horizon_hours]):
                # Extract value from forecast data (assuming format: {"point_time": "...", "value": float})
                value = point.get("value", 0.0)
                forecast_dict[i + 1] = max(0.0, float(value))
            # Fill remaining hours if forecast is shorter than horizon
            for hour in range(len(forecast_dict) + 1, self.horizon_hours + 1):
                forecast_dict[hour] = forecast_dict.get(len(forecast_dict), history[-1] if history else 0.0)
            return forecast_dict

        # Fall back to TCN or trend-based forecasting
        if len(history) < self.seq_len:
            return {hour: history[-1] if history else 0.0 for hour in range(1, self.horizon_hours + 1)}

        if self.trained:
            self.network.eval()
            seq = torch.tensor(history[-self.seq_len :], dtype=torch.float32, device=self.device).unsqueeze(0).unsqueeze(0)
            with torch.no_grad():
                output = self.network(seq)
                last_step = output[:, :, -1]
                prediction = self.projection(last_step).squeeze(0).cpu().numpy()
            return {hour + 1: max(0.0, float(prediction[hour])) for hour in range(self.horizon_hours)}

        window = history[-8:]
        baseline = float(np.mean(window))
        trend = float(window[-1] - window[-2]) if len(window) >= 2 else 0.0
        return {
            hour: max(0.0, baseline + trend * hour * 0.25)
            for hour in range(1, self.horizon_hours + 1)
        }

    def save(self, path: str) -> None:
        torch.save(
            {
                "network_state": self.network.state_dict(),
                "projection_state": self.projection.state_dict(),
            },
            path,
        )

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self.network.load_state_dict(checkpoint["network_state"])
        self.projection.load_state_dict(checkpoint["projection_state"])
        self.trained = True
