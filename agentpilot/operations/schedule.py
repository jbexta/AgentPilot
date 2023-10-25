from datetime import datetime

from agentpilot.utils.helpers import remove_brackets, extract_square_brackets, extract_parentheses, \
    replace_times_with_spoken


class Scheduler:
    def __init__(self, character):
        pass


class Scedule_Item:
    def __init__(self, item_type, when):
        self.item_type = item_type
        self.time_expression = TimeExpression(when)

#
# def switch_keyvals(d):
#     print({v: k for k, v in d.items()})
#     return {v: k for k, v in d.items()}


dates = [
    'first',
    'first',
    'second',
    'third',
    'fourth',
    'fifth',
    'sixth',
    'seventh',
    'eighth',
    'ninth',
    'tenth',
    'eleventh',
    'twelfth',
    'thirteenth',
    'fourteenth',
    'fifteenth',
    'sixteenth',
    'seventeenth',
    'eighteenth',
    'nineteenth',
    'twentieth',
    'twenty-first',
    'twenty-second',
    'twenty-third',
    'twenty-fourth',
    'twenty-fifth',
    'twenty-sixth',
    'twenty-seventh',
    'twenty-eighth',
    'twenty-ninth',
    'thirtieth',
    'thirty-first'
]
months = [
    'January',
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'Septemeber',
    'October',
    'November',
    'December',
]
days = [
    'Monday',
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
]


class TimeExpression:
    def __init__(self, description=None, time_expression=None, base_datetime=None):
        self.time_expression = time_expression
        self.description = description
        if description is not None and time_expression is None:
            self.desc_to_time_expression()
        self.base_datetime = datetime(2023, 1, 1, 1, 1, 1)  # base_datetime
        self.order = ['TIME', 'SECOND', 'MINUTE', 'HOUR', 'DAY', 'WEEK', 'MONTH', 'QUARTER', 'YEAR']

        # self.timeframe_seconds = {
        #     'SECOND': 1,
        #     'MINUTE': 60,
        #     'HOUR': 3600,
        #     'DAY': 86400,
        #     'WEEK': 604800,
        #     'MONTH': 2678400,
        #     'QUARTER': 8035200,
        #     'YEAR': 31536000
        # }
        # self.timeframe_multiples = {
        #     'MINUTE': {
        #         'SECOND': 60,
        #     },
        #     'HOUR': {
        #         'MINUTE': 60,
        #     },
        #     'DAY': {
        #         'HOUR': 24,
        #     },
        #     'WEEK': {
        #         'DAY': 7,
        #     },
        #     'MONTH': {
        #         'DAY': 31,
        #     },
        #     'QUARTER': {
        #         'MONTH': 3,
        #     },
        #     'YEAR': {
        #         'DAY': 365,
        #     }
        # }
        # self.intervals = [0, 60, 3600, 86400, 604800, 3600, 7200, 10800, 14400, 28800, 43200, 86400, 604800]

    def desc_to_time_expression(self):
        self.time_expression = ''  # TODO

    def match_datetime(self, dt):
        # MATCHES IF THE DTIME IS WITHIN OR ON THE TIME EXPRESSION
        dt = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

        segments = self.time_expression.split('.')
        segments = sorted(segments, key=lambda x: self.order.index(remove_brackets(x)))
        # every_timeframe = [0 for _ in range(len(segments))]
        timeframes_success = [0 for _ in range(len(segments))]

        for i, segment in enumerate(segments):
            square_brackets = extract_square_brackets(segment)
            parentheses = extract_parentheses(segment)
            segment_timeframe = remove_brackets(segment)
            if segment_timeframe == '': raise ValueError('Empty segment')

            if not (square_brackets or parentheses):  # if no brackets, then it acts as 1 parenthesis
                parentheses = "1"

            # if parentheses:
            # elif square_brackets:

            if segment_timeframe == 'TIME':
                # segment format = "HH:MM AM/PM"
                # check if the time is within the time expression
                time_dt = datetime.strptime(dt.strftime('%H:%M %p'), '%H:%M %p')
                timeframes_success[i] = 1 if (time_dt.hour == dt.hour and time_dt.minute == dt.minute) else 0
                continue
            # elif segment_timeframe == 'SECOND':
            #     timeframes_success[i] = (dt.second in indexes)  # indexes

            every_n_ticks, for_next_n_ticks = self.split_parenthesis(parentheses)
            indexes, offset = self.split_square_brackets(square_brackets)

    def split_parenthesis(self, parenthesis):  # returns every_n_ticks, for_next_n_ticks
        if parenthesis is None: return None, None
        split = parenthesis.split(':')
        if len(split) == 1:
            return int(parenthesis), -1
        elif len(split) >= 2:
            return int(split[0]), int(split[1])

    def split_square_brackets(self, square_bracket):  # returns indexes,
        if square_bracket is None: return None, None
        range_split = square_bracket.split(':')
        multiple_split = square_bracket.split(',')

        has_range = len(range_split) > 1
        has_multiple = len(multiple_split) > 1
        has_offset = '+' in square_bracket
        if has_range and has_multiple: raise ValueError('Cannot have both range and multiple in square brackets')
        # if has_range and has: raise ValueError('Cannot have both range and multiple in square brackets')

        indexes = []
        offset = None
        if has_multiple:
            indexes = [x for x in multiple_split]
        elif has_range:
            indexes = [int(x) for x in range(int(range_split[0]), int(range_split[1]) + 1)]
            chk = 1
        else:
            indexes = [int(square_bracket)]
            if has_offset:
                offset = int(square_bracket.replace('+', ''))

        return indexes, offset

    def timex_to_english(self):
        # If parse unsuccessful then send to thinker
        segments = self.time_expression.split('.')
        if any([remove_brackets(x) not in self.order for x in segments]):
            return ''
        segments = sorted(segments, key=lambda x: self.order.index(remove_brackets(x)))
        engs = []

        for i, segment in enumerate(segments):
            square_brackets = extract_square_brackets(segment)
            parentheses = extract_parentheses(segment)
            if square_brackets and parentheses: raise ValueError('Both brackets not supported')

            segment_timeframe = remove_brackets(segment)
            if segment_timeframe == '': raise ValueError('Empty segment')
            next_segment_timeframe = remove_brackets(segments[i + 1]) if i + 1 < len(segments) else ''

            if not (square_brackets or parentheses):  # if no brackets, then it acts as 1 parenthesis
                parentheses = "1"

            if segment_timeframe == 'TIME':
                hour_mins = square_brackets.split(':')
                if len(hour_mins) != 2: raise ValueError('Invalid time format')
                spoken_time = replace_times_with_spoken(square_brackets)
                engs.append(spoken_time)
                continue

            every_n_ticks, for_next_n_ticks = self.split_parenthesis(parentheses)
            indexes, offset = self.split_square_brackets(square_brackets)

            if square_brackets:
                use_weekdays = segment_timeframe == 'DAY' and (next_segment_timeframe == 'WEEK' or next_segment_timeframe == '')
                use_months = segment_timeframe == 'MONTH'
                timeframe_str = f' {segment_timeframe}' if not (use_weekdays or use_months) else ''
                engs.append(self.list_to_ranges_spoken(indexes, use_weekdays=use_weekdays, use_months=use_months) + timeframe_str)
            elif parentheses:
                if every_n_ticks == 1:
                    engs.append(f"every {segment_timeframe}")
                else:
                    engs.append(f"every {every_n_ticks} {segment_timeframe}S")
                if for_next_n_ticks != -1:
                    engs.append(f"for the next {for_next_n_ticks} {segment_timeframe}S")

        return ' '.join(engs)

    def list_to_ranges_spoken(self, int_list, use_weekdays=False, use_months=False):
        int_list = sorted(int_list)
        ranges = []
        # prev_element = None
        max_weekday = 7
        max_month = 12

        current_range = None
        for item in int_list:
            int_item = int(item)
            if int_item > max_weekday and use_weekdays: use_weekdays = False
            if int_item > max_month and use_months: use_months = False

            if current_range is None:
                current_range = [int_item]

            elif len(current_range) == 1:
                if int_item == current_range[-1] + 1:
                    current_range.append(int_item)
                else:
                    ranges.append(current_range)
                    current_range = [int_item]

            elif len(current_range) == 2:
                if int_item == current_range[-1] + 1:
                    current_range[-1] = int_item
                else:
                    ranges.append(current_range)
                    current_range = [int_item]
        ranges.append(current_range)

        single_strings = []
        range_strings = []
        for rng in ranges:
            rng_dict = {x: days[x] for x in rng} if use_weekdays else {x: months[x] for x in rng} if use_months else {x: dates[x] for x in rng}
            if len(rng) == 1:
                single_strings.append(str(rng_dict[rng[0]]))
            elif len(rng) == 2:
                if rng[1] - rng[0] == 1:
                    single_strings.append(str(rng_dict[rng[0]]))
                    single_strings.append(str(rng_dict[rng[1]]))
                else:
                    range_strings.append(f"{rng_dict[rng[0]]} to {rng_dict[rng[1]]}")
            else:
                raise ValueError('Invalid range')

            # for i in range(len(rng)):
            #     int_item = rng[i]
            #     if use_weekdays:
            #         rng[i] = days[int_item]
            #     elif use_months:
            #         rng[i] = months[int_item]
            #     else:
            #         rng[i] = dates[int_item]

        return ' and '.join(single_strings + range_strings)
