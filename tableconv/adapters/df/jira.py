from tableconv.adapters.df.base import register_adapter, Adapter


@register_adapter(['jiracloud'], read_only=True)
class JIRAAdapter(Adapter):
    @staticmethod
    def get_example_url(scheme):
        return f'{scheme}://mycorpname'

    @staticmethod
    def load(uri, query):
        raise NotImplementedError  # TODO
