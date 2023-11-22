from agentpilot.utils import sql
from packaging import version

class SQLUpgrade:
    def __init__(self):
        pass

    def v0_1_0(self):
        sql.execute("CREATE TABLE IF NOT EXISTS `apis` (`name` TEXT, `client_key` TEXT, `priv_key` TEXT)")
        sql.execute("CREATE TABLE IF NOT EXISTS `contexts` (`context_id` TEXT, `context_name` TEXT, `context_type` TEXT, `context_config` TEXT, `context_co")
        return '0.1.0'

    def upgrade(self, current_version):
        if current_version < "0.1.0":
            return self.v0_1_0()
        else:
            return current_version
        # add more conditions here for each new version


upgrade_script = SQLUpgrade()
versions = ['0.0.8', '0.1.0']  # list of versions in chronological order
