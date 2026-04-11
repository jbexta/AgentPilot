
from contextlib import contextmanager
from decimal import Decimal
import os
import re
import uuid
import numpy as np
import h5py


# DATA_DIR = '/mnt/storage/DATA/CRY'
DATA_DIR = '/media/jb/DATA'
# DATA_DIR = '/mnt/storage/DATA/CRY'
PRICE_DIR = f'{DATA_DIR}/PRICE'
TA_DIR = f'{DATA_DIR}/TA'
EXTREMA_DIR = f'{TA_DIR}/EXTREMA'


common_metadata = [
    'id',
    'structure',
    'parent',
]

tea_kinds = {
    'ma_analytics': {
        'columns': {
            'unix': 'i8',
            'ma_len': 'i4',          # Which MA (5-400)
            'ma_value': 'f8',        # The actual MA price
            'norm_dist': 'f8',       # Distance normalized by volatility
            'event_break': 'i4',     # 1 if Breakthrough, 0 else
            'event_bounce': 'i4',    # 1 if Bounce, 0 else
            'trend_change': 'i4',    # 1 if Direction changed, 0 else
        },
        'metadata': common_metadata + ['source_candle_id']
    },
    'line': {
        'columns': {
            'unix': 'i8',
            'value': 'f8',
            'price': 'f8',
            'volume': 'f8',
            'market_cap': 'f8',
        },
        'metadata': common_metadata
    },
    'trades': {
        'columns': {
            'unix': 'i8',
            'trade_id': 'i8',
            'price': 'f8',
            'vol_b': 'f8',
            'buyer_is_maker': 'i4',
        },
        'metadata': common_metadata + [
            'api',
            'api_exchange',
            'api_market'
        ],
    },
    'ohlc': {
        'columns': {
            'unix': 'i8',
            'open': 'f8',
            'high': 'f8',
            'low': 'f8',
            'close': 'f8',
            'vol_b': 'f8',
            'vol_q': 'f8',
        },
        'metadata': common_metadata + [
            'interval',
            'api',
            'api_exchange',
            'api_market'
        ]
    },
}


def create_h5_file(path, metadata=None, with_dataset=None, overwrite=False):  #  kind, namevals=None, overwrite=False):
    if metadata is None:
        metadata = {}
    
    if os.path.isfile(path):
        if not overwrite:
            return
        os.remove(path)
    
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with h5py.File(path, 'w') as f:
        for key, value in metadata.items():
            f.attrs[key] = value
        
        if with_dataset is not None:
            create_h5_dataset(f, with_dataset)


def create_h5_dataset(path_or_file, dataset_type, overwrite=False, chunk_rows=20000):
    """
    Create an HDF5 dataset with Gzip compression and optimal chunking.

    Parameters
    ----------
    path_or_file : str or h5py.File
        Path to HDF5 file or open file handle.
    dataset_type : str
        Dataset name/type key from tea_kinds.
    overwrite : bool
        If True, delete existing dataset before creating.
    chunk_rows : int
        Number of rows per chunk (20k ≈ 720 KB for 36-byte rows).
    """
    with h5py_file(path_or_file) as f:
        if dataset_type in f:
            if not overwrite:
                return
            del f[dataset_type]

        # Create a structured dtype from the columns dict
        structure = dataset_type.split('/')[0]
        columns = tea_kinds[structure]['columns']
        dtype_list = [(name, dtype) for name, dtype in columns.items()]

        f.create_dataset(
            dataset_type,
            shape=(0,),
            maxshape=(None,),
            dtype=dtype_list,
            # compression='lzf',
            compression="gzip",  # Better compression ratio
            compression_opts=4,  # Maximum compression level
            chunks=(chunk_rows,),
        )
        f.flush()


@contextmanager
def h5py_file(path_or_file, mode='a'):
    """
    Helper context manager that uses an existing h5py.File object if given,
    or opens/closes a new one otherwise.
    """
    if isinstance(path_or_file, PriceFile):
        yield path_or_file.file
    elif isinstance(path_or_file, h5py.File):
        yield path_or_file
    else:
        with h5py.File(path_or_file, mode) as file:
            yield file

            
class PriceFile:
    """
    Represents a .h5 file that can contain the datasets:
    - trades
    - ohlc/60
    - ohlc/180
    - indicators/60/SMA
    - indicators/60/EMA
    - indicators/60/RSI

    Methods:
    - generate_intervals()
    - generate_indicator
    """
    intervals = {
        60: '1m',
        180: '3m',
        300: '5m',
        900: '15m',
        1800: '30m',
        3600: '1h',
        7200: '2h',
        14400: '4h',
        21600: '6h',
        43200: '12h',
        86400: '1D',
        604800: '1W',
        2592000: '1M',
        31536000: '1Y',
    }
    def __init__(self, path, mode='a'):
        self.path = path
        self.mode = mode
        self._file = None
        with h5py.File(path, 'r') as f:
            if 'trades' in f:
                self.base_interval = 0
            elif 'ohlc' in f:
                self.base_interval = int(list(f['ohlc'].keys())[0])
            elif 'data' in f:  # treat as line for now
                self.base_interval = None
            else:
                raise ValueError(f"No trades or ohlc or data datasets found in {path}")
    
    def __enter__(self):
        try:
            self._file = h5py.File(self.path, self.mode)
        except OSError as e:
            raise RuntimeError(f"Failed to open HDF5 file: {self.path}") from e
        return self._file   # return the wrapper so we can add methods

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # do NOT suppress exceptions
    
    def close(self) -> None:
        """Close the underlying HDF5 file if it is open."""
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None

    @property
    def file(self) -> h5py.File:
        """Access the underlying h5py file object."""
        # if self._file is None:
        #     raise RuntimeError("File is not open. Use a 'with PriceFile(...)' block or call __enter__() first.")
        return self._file
    
    @property
    def metadata(self):
        path_or_file = self.file if self.file is not None else self.path
        with h5py_file(path_or_file) as f:
            return {k: v for k, v in f.attrs.items()}
    
    @metadata.setter
    def metadata(self, metadata):
        path_or_file = self.file if self.file is not None else self.path
        with h5py_file(path_or_file) as f:
            for k, v in metadata.items():
                f.attrs[k] = v

    def append_batch(self, data_batch, generate_operations=True):
        path_or_file = self.file if self.file is not None else self.path
        dataset_name = 'trades' if self.base_interval == 0 else f'ohlc/{self.base_interval}'
        append_h5_dataset(path_or_file, dataset_name, data_batch)
        # if generate_operations:
        #     self.generate_intervals()

    def get_available_intervals(self):
        path_or_file = self._file if self.file is not None else self.path
        with h5py_file(path_or_file, 'r') as f:
            if 'ohlc' in f:
                all_intervals = sorted([int(k) for k in f['ohlc'].keys()])
                zipped = zip(all_intervals, [self.intervals[i] for i in all_intervals])
                return dict(zipped)
        return {}
    
    def get_interval_data(self, interval):
        """Return OHLC and all indicators for a given interval"""
        path_or_file = self.file if self.file is not None else self.path
        with h5py_file(path_or_file, 'r') as f:
            dataset_name = f'ohlc/{interval}'
            if dataset_name not in f:
                raise ValueError(f"Interval {interval} not found in {path_or_file}")
            dataset = f[dataset_name][:]
            indicators = {}
            if 'indicators' in f:
                for indicator in f['indicators'].keys():
                    indicators[indicator] = f[f'indicators/{indicator}']
            return dataset, indicators
    
    def binary_search_unix_price(self, unix):
        path_or_file = self.file if self.file is not None else self.path
        with h5py_file(path_or_file, 'r') as f:
            interval = 60 if self.base_interval == 0 else self.base_interval
            dataset = f['ohlc'][str(interval)]

            if dataset.shape[0] == 0:
                raise ValueError(f"No data found in {path_or_file}")

            left = 0
            right = dataset.shape[0] - 1
            while left < right:
                mid = (left + right) // 2
                if dataset[mid]['unix'] < unix:
                    left = mid + 1
                else:
                    right = mid
            
            if left > dataset.shape[0] - 2:
                raise ValueError(f"Unix {unix} is greater than the last unix in the dataset")
            elif left == 0:
                raise ValueError(f"Unix {unix} is less than the first unix in the dataset")

            nearest_candle = dataset[left]
            nearest_candle_unix = nearest_candle['unix']
            # nearest_candle_left = dataset[left - 1]
            # nearest_candle_right = dataset[left + 1]
            # nearest_candle_left_unix = nearest_candle_left['unix']
            # nearest_candle_right_unix = nearest_candle_right['unix']

            diff = abs(nearest_candle_unix - unix)
            if nearest_candle_unix >= unix:
                if diff > interval * 10:
                    raise ValueError(f"Unix {unix} is more than 2 candles away from the nearest candle")
                return nearest_candle['open']
            elif nearest_candle_unix < unix:
                if diff > interval * 10:
                    raise ValueError(f"Unix {unix} is more than 2 candles away from the nearest candle")
                return nearest_candle['close']

    
    # def get_data_at_unix(self, unix):
    #     # next interval after base_interval that is greater than 0
    #     lowest_interval = next(interval for interval in self.intervals.keys() if interval > self.base_interval)
    #     return self.get_interval_data(lowest_interval)

    def generate_intervals(self):
        """
        Generate OHLC candles for all intervals from trade data.

        Continuous: preserves existing OHLC data and processes only new data
        starting from the last unix in each dataset (reprocessing that last
        candle to handle incomplete data).
        """
        # All target intervals (seconds)

        sorted_intervals = sorted(self.intervals.keys())
        parent_map = {}

        for interval in sorted_intervals:
            # pick the largest smaller interval that divides this one
            possible_parents = [i for i in sorted_intervals if i < interval and interval % i == 0]
            if not possible_parents:
                parent_map[interval] = 0
            else:
                parent_map[interval] = max(possible_parents)

        OHLC_CHUNK = 1_000_000

        path_or_file = self.file if self.file is not None else self.path
        with h5py_file(path_or_file, 'a') as f:

            # ensure ohlc group exists (but preserve existing data)
            if 'ohlc' not in f:
                f.create_group('ohlc')
                f.flush()

            for target_interval in sorted_intervals:
                target_ds_name = f'ohlc/{target_interval}'
                parent_interval = parent_map[target_interval]
                parent_is_trades = parent_interval == 0
                target_interval_B = target_interval

                # create target dataset if it doesn't exist
                if target_ds_name not in f:
                    # ohlc_dtype = [(name, dtype) for name, dtype in tea_kinds['ohlc']['columns'].items()]
                    create_h5_dataset(f, target_ds_name)

                target_ds = f[target_ds_name]

                # get dataset handle
                if parent_is_trades:
                    parent = f['trades']
                    target_interval_B = target_interval * 1_000_000_000  # convert to nanoseconds for trades
                else:
                    parent = f[f'ohlc/{parent_interval}']

                n = len(parent)
                if n == 0:
                    continue

                # Determine start offset from existing data
                start_offset = 0
                existing_len = len(target_ds)
                if existing_len > 0:
                    last_unix = int(target_ds[-1]['unix'])
                    # Remove last row to reprocess it (may be incomplete)
                    target_ds.resize((existing_len - 1,))
                    # Convert to parent units and binary search
                    last_unix_parent = last_unix * 1_000_000_000 if parent_is_trades else last_unix
                    # Binary search to find the insertion index for last_unix_parent
                    left = 0
                    right = n
                    while left < right:
                        mid = (left + right) // 2
                        if parent[mid]['unix'] < last_unix_parent:
                            left = mid + 1
                        else:
                            right = mid
                    start_offset = left
                current = None  # carries across chunks  # [gstart, open, high, low, close, vol_b, vol_q]

                for start in range(start_offset, n, OHLC_CHUNK):
                    end = min(start + OHLC_CHUNK, n)

                    # Read entire chunk once to avoid repeated decompression
                    chunk = parent[start:end]

                    unix = chunk['unix'].astype(np.int64)
                    g = (unix // target_interval_B) * target_interval

                    if parent_is_trades:
                        o = h = l = c = chunk['price'].astype(np.float64)
                        vb = chunk['vol_b'].astype(np.float64)
                        vq = o * vb
                    else:
                        o  = chunk['open'].astype(np.float64)
                        h  = chunk['high'].astype(np.float64)
                        l  = chunk['low'].astype(np.float64)
                        c  = chunk['close'].astype(np.float64)
                        vb = chunk['vol_b'].astype(np.float64)
                        vq = chunk['vol_q'].astype(np.float64)

                    # # ======================================================
                    # # GROUP BY g USING NUMPY — NO PYTHON PER-ROW LOOP
                    # # ======================================================

                    # 1) find start indices of each group
                    starts = np.flatnonzero(np.diff(g)) + 1
                    group_idx = np.r_[0, starts]          # IMPORTANT: do NOT append len(g)

                    # 2) group starts (actual timestamp for each candle)
                    group_starts = g[group_idx]

                    # 3) vectorized OHLCV aggregation
                    opens  = o[group_idx]
                    highs  = np.maximum.reduceat(h, group_idx)
                    lows   = np.minimum.reduceat(l, group_idx)
                    closes = c[np.r_[group_idx[1:] - 1, len(c)-1]]   # last element of each group

                    vol_b = np.add.reduceat(vb, group_idx)
                    vol_q = np.add.reduceat(vq, group_idx)

                    # ======================================================
                    # Stitch with previous chunk's last candle
                    # ======================================================
                    out = []

                    for i in range(len(group_starts)):
                        gs = int(group_starts[i])
                        o0 = float(opens[i])
                        h0 = float(highs[i])
                        l0 = float(lows[i])
                        c0 = float(closes[i])
                        vb0 = float(vol_b[i])
                        vq0 = float(vol_q[i])

                        if current is None:
                            current = [gs, o0, h0, l0, c0, vb0, vq0]
                            continue

                        if current[0] == gs:
                            # same candle → merge
                            current[2] = max(current[2], h0)
                            current[3] = min(current[3], l0)
                            current[4] = c0
                            current[5] += vb0
                            current[6] += vq0
                        else:
                            # flush old, start new
                            out.append(tuple(current))
                            current = [gs, o0, h0, l0, c0, vb0, vq0]

                    # Write all completed candles
                    if out:
                        append_h5_dataset(f, target_ds_name, out)

                # ----------------------------------------------------------
                # Flush last candle
                # ----------------------------------------------------------
                if current is not None:
                    append_h5_dataset(f, target_ds_name, [tuple(current)])
    
    def generate_indicator(self):
        pass

    def get_interval(self, interval):
        pass


def normalize_timestamp(ts: int) -> int:
    """
    Normalize a Unix timestamp in unknown units (s, ms, µs, ns)
    into nanoseconds. Returns an integer.

    Assumes the timestamp is 1970+ and within realistic ranges.
    """
    if ts < 1e11:
        # seconds → ns
        return ts * 1_000_000_000
    elif ts < 1e14:
        # milliseconds → ns
        return ts * 1_000_000
    elif ts < 1e17:
        # microseconds → ns
        return ts * 1_000
    elif ts < 1e20:
        # nanoseconds → ns
        return ts
    else:
        raise ValueError(f"Timestamp {ts} is out of range")


def append_h5_dataset(path_or_file, dataset_name, data):
    with h5py_file(path_or_file) as f:
        # structure = 'raw' if dataset_name == 'trades' else 'ohlc'  # file_info['structure']
        structure = dataset_name.split('/')[0]
        columns = tea_kinds[structure]['columns']
        dtype_list = [(name, dtype) for name, dtype in columns.items()]
        data_array = np.array([tuple(row) for row in data], dtype=dtype_list)
        if dataset_name not in f:
            create_h5_dataset(f, dataset_name)

        dataset = f[dataset_name]
        current_size = dataset.shape[0]
        new_size = current_size + len(data_array)
        dataset.resize((new_size,))
        dataset[current_size:] = data_array
        f.flush()


def get_h5_dataset_last_item_cell(path_or_file, dataset_name, column_name, default=None):
    with h5py_file(path_or_file) as f:
        dataset = f[dataset_name]
        if dataset.shape[0] == 0:
            return default
        return dataset[-1][column_name]


def get_h5_dataset_first_item_cell(path_or_file, dataset_name, column_name, default=None):
    with h5py_file(path_or_file) as f:
        dataset = f[dataset_name]
        if dataset.shape[0] == 0:
            return default
        return dataset[0][column_name]


def get_h5_file_info(path):
    try:  # temp
        with h5py.File(path, 'r') as f:
            dataset = f['data']
            metadata = {k: dataset.attrs[k] for k in dataset.attrs.keys()}

            item_count = dataset.shape[0]
            if item_count == 0:
                return metadata

            first_item = dataset[0]
            last_item = dataset[item_count - 1]

            structure = metadata['structure']
            
            columns = list(tea_kinds[structure]['columns'])
            unix_column = columns.index('unix')
            metadata['start_unix'] = first_item[unix_column]
            metadata['end_unix'] = last_item[unix_column]

            # if structure == 'raw':
            #     # metadata['last_price'] = last_item['price']
            #     trade_id_column = columns.index('trade_id')
            #     metadata['last_trade_id'] = last_item[trade_id_column]

            # elif structure == 'ohlc':
            #     metadata['last_price'] = last_item['close']

            # elif structure == 'line':
            #     metadata['last_price'] = last_item['price']
            #     metadata['last_market_cap'] = last_item['market_cap']

            # elif structure == 'extrema':
            #     metadata['last_indx'] = last_item['indx']
            #     metadata['last_tfindx'] = last_item['tfindx']
            #     metadata['last_unix'] = last_item['unix']
            #     metadata['last_extype'] = last_item['extype']
            #     metadata['last_exprice'] = last_item['exprice']

            return metadata
    except Exception as e:
        print(f"Error getting h5 file info: {e}")
        return {}


def sanitize_string(s):
    return re.sub("[^A-Za-z0-9_-]+", '', str(s))


def sanitize_filename(s):
    return re.sub("[^A-Za-z0-9_() -]+", '', str(s))


def get_h5_path(api, market):
    market = sanitize_string(market)
    file_name = f'{api}_{market}.h5'
    nodes = [PRICE_DIR, sanitize_string(api)]
    # if api_exch is not None:
    #     nodes.insert(2, sanitize_string(api_exch))

    folder_path = os.path.join(*nodes)
    return os.path.join(folder_path, file_name)
