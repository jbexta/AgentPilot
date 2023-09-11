from openagent.operations.action import BaseAction, ActionInput, ActionResult
from openagent.toolkits import lists


class ViewOrRead_Existing_List(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='whats on my shopping list')
        self.desc_prefix = 'Asked about '
        self.desc = 'Information on an existing list or lists'
        self.inputs.add('list-name')

    def run_action(self):
        return True


class Create_A_New_List(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='create a new list')
        self.desc_prefix = 'requires me to'
        self.desc = 'Create a new list'
        self.inputs.add('list-name')

    def run_action(self):
        list_name = self.inputs.get('list-name').value
        try:
            lists.add_list(list_name)
            yield ActionResult(f'[SAY] "A new list called {list_name} has been created."')
        except Exception as e:
            yield ActionResult(f'[SAY] "There was an error creating the list"')


class DeleteOrRemove_A_List(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='delete my shopping list')
        self.desc_prefix = 'requires me to'
        self.desc = 'Delete/Remove an item from a list'
        self.inputs.add('list-name')

    def run_action(self):
        self.inputs.add('are-you-sure-you-want-to-delete-the-list', format='Boolean (True/False)')
        if not self.inputs.all_filled():
            yield ActionResult('[SAY] "Are you sure you want to delete the list?"', code=300)
        yield ActionResult(f"[SAY] Deleted the list")


class Add_Item_To_List(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='add milk to my shopping list')
        self.desc_prefix = 'requires me to'
        self.desc = 'Add something to a list'
        self.inputs.add('which-list/s')
        self.inputs.add('what_to_add')

    def run_action(self):
        list_name = self.inputs.get(0).value
        item = self.inputs.get(1).value
        yield ActionResult(f"[SAY]{item} has been added to the list '{list_name}'")
        # return True


class DeleteOrRemove_Item_From_List(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='remove milk from my shopping list')
        self.desc_prefix = 'requires me to'
        self.desc = 'Delete/Remove an item from a list'
        self.inputs.add('list-name')
        self.inputs.add('item')

    def run_action(self):
        yield ActionResult(f"[SAY]Item has been removed from the list")
