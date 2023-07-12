#!/usr/bin/env python3

from apstra_bp_consolidation.apstra_session import CkApstraSession

class CkApstraBlueprint:

    def __init__(self, session: CkApstraSession, label: str) -> None:
        """
        Initialize a CkApstraBlueprint object.

        Args:
            session: The Apstra session object.
            label: The label of the blueprint.
        """
        self.session = session
        self.label = label
        self.id = None
        self.get_id()
        self.url_prefix = f"{self.session.url_prefix}/blueprints/{self.id}"

    def get_id(self) -> str:
        """
        Get the ID of the blueprint.

        Returns:
            The ID of the blueprint.
        """
        url = f"{self.session.url_prefix}/blueprints"
        blueprints = self.session.session.get(url).json()['items']
        for blueprint in blueprints:
            if blueprint['label'] == self.label:
                self.id = blueprint['id']
                break
        if self.id is None:
            raise ValueError(f"Blueprint '{self.label}' not found.")
        return self.id

    def print_id(self) -> None:
        """
        Print the ID of the blueprint.
        """
        print(f"Blueprint ID: {self.id}")

    def query(self, query: str) -> list:
        """
        Query the Apstra API.

        Args:
            query: The query string.

        Returns:
            The results of the query.
        """
        url = f"{self.url_prefix}/qe"
        payload = {
            "query": query
        }
        response = self.session.session.post(url, json=payload)
        # print (f"{query=}, {response.json()=}")
        return response.json()['items']
    
    # return the first entry for the system
    def get_system_with_im(self, label):
        return self.query(f"node('system', label='{label}', name='system').out().node('interface_map', name='im')")[0]


    def add_generic_system(self, gs_spec: dict) -> list:
        """
        Add a generic system to the blueprint.

        Args:
            gs_spec: The specification of the generic system.

        Returns:
            The ID of the switch-system-link ids.
        """
        url = f"{self.url_prefix}/switch-system-links"
        created_generic_system = self.session.session.post(url, json=gs_spec)
        if created_generic_system is None or len(created_generic_system.json()) == 0 or 'ids' not in created_generic_system.json():
            # raise ValueError(f"Error creating generic system: {created_generic_system=}")
            print(f"Generic system not created: {created_generic_system=}")
            return []
        print(f"{created_generic_system.json()=}")
        return created_generic_system.json()['ids']

    def patch_leaf_server_link(self, link_spec: dict) -> None:
        """
        Patch a leaf-server link.

        Args:
            link_spec: The specification of the leaf-server link.
        """
        url = f"{self.url_prefix}/leaf-server-link-labels"
        self.session.session.patch(url, json=link_spec)

    def patch_obj_policy_batch_apply(self, policy_spec, params=None):
        '''
        Apply policies in a batch
        '''
        return self.session.session.patch(f"{self.url_prefix}/obj-policy-batch-apply", json=policy_spec, params=params)

    def batch(self, batch_spec: dict, params=None) -> None:
        '''
        Run API commands in batch
        '''
        url = f"{self.url_prefix}/batch"
        self.session.session.post(url, json=batch_spec, params=params)

    def cts_single_ae_generic_system(self, gs_label) -> list:
        '''
        Get the CTS of generic system with single AE
        '''
        ct_list_spec = f"match(node('system', label='{gs_label}').out().node('interface', if_type='port_channel', name='ae2').out().node('link').in_().node(name='ae1').out().node('ep_group').in_().node('ep_application_instance').out().node('ep_endpoint_policy', policy_type_name='batch', name='batch').where(lambda ae1, ae2: ae1 != ae2 )).distinct(['batch'])"
        ct_list = [ x['batch']['id'] for x in self.query(ct_list_spec) ]
        return ct_list

    def revert(self):
        '''
        Revert the blueprint
        '''
        url = f"{self.url_prefix}/revert"
        revert_result = self.session.session.post(url, json="", params={"aync": "full"})
        print(f"Revert result: {revert_result.json()}")


if __name__ == "__main__":
    apstra = CkApstraSession("10.85.192.50", 443, "admin", "zaq1@WSXcde3$RFV")
    bp = CkApstraBlueprint(apstra, "pslab")
    bp.print_id()
