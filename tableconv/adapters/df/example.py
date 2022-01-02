# import pandas as pd

# from tableconv.adapters.df.base import Adapter, register_adapter


# @register_adapter(['example'], read_only=True)
# class ExampleDataAdapter(Adapter):
#     @staticmethod
#     def get_example_url(scheme):
#         return f'{scheme}://'

#     @staticmethod
#     def load(uri, query):
#         return pd.DataFrame.from_records([(i,) for i in range(10)], columns=['value'])
