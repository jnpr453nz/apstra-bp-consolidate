#!/usr/bin/env python3

import json
import time

from apstra_bp_consolidation.apstra_session import CkApstraSession
from apstra_bp_consolidation.apstra_blueprint import CkApstraBlueprint




def pull_generic_system(tor_bp, switch_label_pair: list) -> dict:
    """
    Pull the generic system from the TOR blueprint.

    Args:
        tor_bp: The blueprint object.
        switch_label_pair: The switch pair to pull the generic system from.    

    <generic_system_label>:
        <link_id>:
            gs_if_name: None
            sw_if_name: xe-0/0/15
            sw_label: leaf15
            speed: 10G
            aggregate_link: <aggregate_link_id>
            tags: []
    """
    print(f"==== Pulling generic system connected to {switch_label_pair=} of blueprint {tor_bp.label} ====")
    generic_systems_data = {}
    # generic systems data with member interfaces on both sides.
    generic_systems = tor_bp.query(f"node('system', role='generic', name='generic').out().node('interface', name='gs_intf').out().node('link', name='link').in_().node(name='sw_intf').in_().node('system', label=is_in({switch_label_pair}), name='switch').where(lambda gs_intf, sw_intf: gs_intf != sw_intf)")
    # aggregate links to associate them to the member interfaces
    aggregate_links = tor_bp.query(f"match(node('link', link_type='aggregate_link', name='aggregate_link').in_().node().out().node(name='member_interface').out().node('link', name='member_link').in_().node().in_().node('system', label=is_in({switch_label_pair})),node(name='aggregate_link').in_().node('interface').in_().node('system', name='system'))")
    for gs in generic_systems:
        # TODO: generalize upglinks processing
        # most QFX5120 has port 48 and 49 as uplinks
        if gs['sw_intf']['if_name'] in ["et-0/0/48", "et-0/0/49"]:
            # those are uplinks
            continue
        generic_system_label = gs['generic']['label']
        link_id = gs['link']['id']
        # create entry for this generic system if it doesn't exist
        if generic_system_label not in generic_systems_data.keys():
            generic_systems_data[generic_system_label] = {}
        this_data = {'tags': []}
        this_data['sw_label'] = gs['switch']['label']
        this_data['sw_if_name'] = gs['sw_intf']['if_name']
        this_data['speed'] = gs['link']['speed']
        # register this data as the link id
        generic_systems_data[generic_system_label][link_id] = this_data
        # pretty_yaml(generic_systems_data, "generic_systems_data")
    # update the aggregate link id on the associated member links
    for al in aggregate_links:
        if al['system']['label'] not in generic_systems_data.keys():
            # those may be uplinks
            continue
        generic_systems_data[al['system']['label']][al['member_link']['id']]['aggregate_link'] = al['aggregate_link']['id']
    # retrieve the tags information
    # link_tags = tor_bp.query("node('system', role='generic', name='generic_system').out().node('interface').out().node('link', link_type='ethernet', name='link').in_().node('tag', name='tag')")
    link_tags = tor_bp.query(f"match(node('tag', name='tag').out().node('link', name='member_link').in_().node('interface').in_().node('system', label=is_in({switch_label_pair}), name='switch'), node('system', role='generic', name='generic_system').out().node('interface').out().node('link', name='member_link'))")
    for tag in link_tags:
        generic_system_label = tag['generic_system']['label']
        member_link_id = tag['member_link']['id']
        tag_value = tag['tag']['label']
        if tag['generic_system']['label'] not in generic_systems_data.keys():
            # this shouldn't happen
            continue
        generic_systems_data[generic_system_label][member_link_id]['tags'].append(tag_value)
    # print(f"==== generic systems pulled: {len(generic_systems_data)}, {generic_systems_data=}")
    print(f"====== generic systems pulled from {tor_bp.label}: {len(generic_systems_data)}")
    # generic_system_label.link.dict
    return generic_systems_data

# generic system data: generic_system_label.link.dict
def new_generic_systems(main_bp, generic_systems_data:dict) -> dict:
    """
    Create new generic systems in the main blueprint based on the generic systems in the TOR blueprint. 
        <generic_system_label>:
            <link_id>:
                gs_if_name: None
                sw_if_name: xe-0/0/15
                sw_label: leaf15
                speed: 10G
                aggregate_link: <aggregate_link_id>
                tags: []


    """
    # to cache the system id of the systems includin leaf
    print(f"==== Creating new generic systems in {main_bp.label} for {len(generic_system_data)} ====")
    system_id_cache = {}

    for generic_system_label, generic_system_data in generic_systems_data.items():
        if main_bp.get_system_id(generic_system_label):
            # this generic system already exists
            print(f"====== skip: new_generic_systems() {generic_system_label} already exists in the main blueprint")
            continue
        generic_system_spec = {
            'links': [],
            'new_systems': [],
        }
        for link_id, link_data in generic_system_data.items():
            link_spec = {
                'lag_mode': None,
                'system': {
                    'system_id': None
                },
                'switch': {
                    'system_id': main_bp.get_system_id(link_data['sw_label']),
                    'transformation_id': main_bp.get_transformation_id(link_data['sw_label'], link_data['sw_if_name'] , link_data['speed']),
                    'if_name': link_data['sw_if_name'],
                }                
            }
            generic_system_spec['links'].append(link_spec)
        new_system = {
            'system_type': 'server',
            'label': generic_system_label,
            'hostname': None, # hostname should not have '_' in it
            'port_channel_id_min': 0,
            'port_channel_id_max': 0,
            'logical_device': {
                'display_name': f"auto-{link_data['speed']}x{len(generic_system_data)}",
                'id': f"auto-{link_data['speed']}x{len(generic_system_data)}",
                'panels': [
                    {
                        'panel_layout': {
                            'row_count': 1,
                            'column_count': len(generic_system_data),
                        },
                        'port_indexing': {
                            'order': 'T-B, L-R',
                            'start_index': 1,
                            'schema': 'absolute'
                        },
                        'port_groups': [
                            {
                                'count': len(generic_system_data),
                                'speed': {
                                    'unit': link_data['speed'][-1:],
                                    'value': int(link_data['speed'][:-1])
                                },
                                'roles': [
                                    'leaf',
                                    'access'
                                ]
                            }
                        ]
                    }
                ]
            }
        }
        generic_system_spec['new_systems'].append(new_system)
        # pretty_yaml(generic_system_spec, generic_system_label)
        print(f"====== new_generic_systems() adding {generic_system_label} to the main blueprint")
        main_bp.add_generic_system(generic_system_spec)

# generic system data: generic_system_label.link.dict
def update_generic_systems_lacp(main_bp, switch_label_pair, tor_generic_systems_data):
    """
    Update LAG mode for the new generic systems
    """
    main_generic_system_data = pull_generic_system(main_bp, switch_label_pair)
    # for generec_system_label, generic_system in generic_systems_data.items():
    #     lag_data = {} # group_label: [ links ]        
    #     for link_label, link_data in { k: v for k, v in generic_system.items() if 'aggregate_link' in v }.items():
    #         lag_data[link_data['aggregate_link']] = link_label
    pass


def build_switch_fabric_links_dict(links_dict:dict) -> dict:
    '''
    Build "links" data from the links query
    It is assumed that the interface names are in et-0/0/48-b format
    '''
    # print(f"==== build_switch_fabric_links_dict() {len(links_dict)=}, {links_dict=}")
    link_candidate = {
            "lag_mode": "lacp_active",
            "system_peer": None,
            "switch": {
                "system_id": links_dict['leaf']['id'],
                "transformation_id": 2,
                "if_name": links_dict['leaf_intf']['if_name']
            },
            "system": {
                "system_id": None,
                "transformation_id": 1,
                "if_name": None
            }
        }
    original_intf_name = links_dict['gs_intf']['if_name']
    if original_intf_name in ['et-0/0/48-a', 'et-0/0/48a']:
        link_candidate['system_peer'] = 'first'
        link_candidate['system']['if_name'] = 'et-0/0/48'
    elif original_intf_name in ['et-0/0/48-b', 'et-0/0/48b']:
        link_candidate['system_peer'] = 'second'
        link_candidate['system']['if_name'] = 'et-0/0/48'
    elif original_intf_name in ['et-0/0/49-a', 'et-0/0/49a']:
        link_candidate['system_peer'] = 'first'
        link_candidate['system']['if_name'] = 'et-0/0/49'
    elif original_intf_name in ['et-0/0/49-b', 'et-0/0/49b']:
        link_candidate['system_peer'] = 'second'
        link_candidate['system']['if_name'] = 'et-0/0/49'
    else:
        return None
    return link_candidate

#     # old_generic_system_physical_links has a list of dict with generic, gs_intf, link, leaf_intf, and leaf 
def build_switch_pair_spec(old_generic_system_physical_links, old_generic_system_label) -> dict:
    # print(f"==== build_switch_pair_spec() with {len(old_generic_system_physical_links)=}, {old_generic_system_label}")
    # print(f"===== build_switch_pair_spec() {old_generic_system_physical_links[0]=}")
    switch_pair_spec = {
        "links": [build_switch_fabric_links_dict(x) for x in old_generic_system_physical_links],
        "new_systems": None
    }

    with open('./tests/fixtures/switch-system-links-5120.json', 'r') as file:
        sample_data = json.load(file)

    switch_pair_spec['new_systems'] = sample_data['new_systems']
    switch_pair_spec['new_systems'][0]['label'] = old_generic_system_label

    # del switch_pair_spec['new_systems']
    print(f"====== build_switch_pair_spec() from {len(old_generic_system_physical_links)=}")
    return switch_pair_spec




def pretty_yaml(data: dict, label: str) -> None:
    print(f"==== {label}\n{yaml.dump(data)}\n====")

def main(apstra: str, config: dict):
    pretty_yaml(config, "config")

    ########
    # prepare the data with initial validation    
    main_bp = CkApstraBlueprint(apstra, config['blueprint']['main']['name'])
    tor_bp = CkApstraBlueprint(apstra, config['blueprint']['tor']['name'])
    access_switch_interface_map_label = config['blueprint']['tor']['new_interface_map']
    
    old_generic_system_label = config['blueprint']['tor']['torname']
    switch_label_pair = [ f"{old_generic_system_label}a", f"{old_generic_system_label}b"]
    
    # find the ae information for the old generic system in the main blueprint
    old_generic_system_ae_query = f"node('system', label='{old_generic_system_label}').out().node('interface', if_type='port_channel', name='ae2').out().node('link').in_().node(name='ae1').where(lambda ae1, ae2: ae1 != ae2 )"
    old_generic_system_ae_list = main_bp.query(old_generic_system_ae_query, print_prefix="main: old_generic_system_ae_query")
    # the generic system should exist in main blueprint
    if len(old_generic_system_ae_list):
        old_generic_system_ae_id = old_generic_system_ae_list[0]['ae1']['id']
    print(f"== main: {old_generic_system_ae_list=}")

    # return

    cts = main_bp.cts_single_ae_generic_system(old_generic_system_label)

    # capture links to the target old generic system in the main blueprint
    old_generic_system_physical_links_query = f"node('system', label='{old_generic_system_label}', name='generic').out().node('interface', if_type='ethernet', name='gs_intf').out().node('link', name='link').in_().node('interface', name='leaf_intf').in_().node('system', name='leaf').where(lambda gs_intf, leaf_intf: gs_intf != leaf_intf)"
    print(f"== main: {old_generic_system_physical_links_query=}")
    # old_generic_system_physical_links has a list of dict with generic, gs_intf, link, leaf_intf, and leaf 
    old_generic_system_physical_links = main_bp.query(old_generic_system_physical_links_query)

    print(f"== main: about to call build_switch_pair_spec, {len(old_generic_system_physical_links)=}")
    switch_pair_spec = build_switch_pair_spec(old_generic_system_physical_links, old_generic_system_label)
    print(f"== main: {switch_pair_spec['links']=}")

    pull_generic_system_data = pull_generic_system(tor_bp, switch_label_pair)
    # pretty_yaml(pull_generic_system_data, "pull_generic_system_data")


    # revert any staged changes
    # main_bp.revert()
    # tor_bp.revert()

    ########
    # delete the old generic system in main blueprint
    # all the CTs on old generic system are on the AE link
    if len(old_generic_system_ae_list):
        old_generic_system_label = config['blueprint']['tor']['torname']
        old_generic_system_ae_list = main_bp.query(f"node('system', label='{old_generic_system_label}').out().node('interface', if_type='port_channel', name='ae2').out().node('link').in_().node(name='ae1').where(lambda ae1, ae2: ae1 != ae2 )")
        if len(old_generic_system_ae_list) == 0:
            print(f"Generic system {old_generic_system_label} not found")
            return
        old_generic_system_ae_id = old_generic_system_ae_list[0]['ae1']['id']
        print(f"{old_generic_system_ae_id=}")

        cts = main_bp.cts_single_ae_generic_system(old_generic_system_label)

        # old_generic_system_physical_links has a list of dict with generic, gs_intf, link, leaf_intf, and leaf 
        # old_generic_system_physical_links = main_bp.query(f"node('system', label='{old_generic_system_label}').out().node('interface', if_type='ethernet').out().node('link', name='link')")
        old_generic_system_physical_links = main_bp.query(f"node('system', label='{old_generic_system_label}').out().node('interface', if_type='ethernet', name='gs_intf').out().node('link', name='link').in_().node('interface', name='leaf_intf').in_().node('system', name='leaf').where(lambda gs_intf, leaf_intf: gs_intf != leaf_intf)")


        # damping CTs in chunks
        while len(cts) > 0:
            cts_chunk = cts[:50]
            print(f"Removing Connecitivity Templates on this links: {len(cts_chunk)=}")
            batch_ct_spec = {
                "operations": [
                    {
                        "path": "/obj-policy-batch-apply",
                        "method": "PATCH",
                        "payload": {
                            "application_points": [
                                {
                                    "id": old_generic_system_ae_id,
                                    "policies": [ {"policy": x, "used": False} for x in cts_chunk]
                                }
                            ]
                        }
                    }
                ]
            }
            batch_result = main_bp.batch(batch_ct_spec, params={"comment": "batch-api"})
            del cts[:50]

        batch_link_spec = {
            "operations": [
                {
                    "path": "/delete-switch-system-links",
                    "method": "POST",
                    "payload": {
                        "link_ids": [ x['link']['id'] for x in old_generic_system_physical_links ]
                    }
                }
            ]
        }
        batch_result = main_bp.batch(batch_link_spec, params={"comment": "batch-api"})
        print(f"{batch_result=}")
        while True:
            if_generic_system_present = main_bp.query(f"node('system', label='{old_generic_system_label}')")
            if len(if_generic_system_present) == 0:
                break
            print(f"== main: {if_generic_system_present=}")
            time.sleep(3)
            




    ########
    # create new access system pair
    # olg logical device is not useful anymore
    # logical_device_list = tor_bp.query("node('system', name='system', role=not_in(['generic'])).out().node('logical_device', name='ld')")
    # logical_device_id = logical_device_list[0]['ld']['id']

    # LD _ATL-AS-Q5100-48T, _ATL-AS-5120-48T created
    # IM _ATL-AS-Q5100-48T, _ATL-AS-5120-48T created
    # rack type _ATL-AS-5100-48T, _ATL-AS-5120-48T created and added
    # ATL-AS-LOOPBACK with 10.29.8.0/22

    existing_switches = main_bp.query(f"node('system', label='{old_generic_system_label}a', name='system')")
    if len(existing_switches) == 0:
        access_switch_pair_created = main_bp.add_generic_system(switch_pair_spec)
        print(f"{access_switch_pair_created=}")

        # wait for the new systems to be created
        while True:
            new_systems = main_bp.query(f"node('link', label='{access_switch_pair_created[0]}', name='link').in_().node('interface').in_().node('system', name='leaf').out().node('redundancy_group', name='redundancy_group')")
            # There should be 5 links (including the peer link)
            if len(new_systems) == 2:
                break
            print(f"Waiting for new systems to be created: {len(new_systems)=}")
            time.sleep(3)
        # The first entry is the peer link
        # rename redundancy group
        main_bp.patch_node(new_systems[0]['redundancy_group']['id'], {"label": f"{old_generic_system_label}-pair" })
        # rename each access switch for the label and hostname
        for leaf in new_systems:
            given_label = leaf['leaf']['label']
            if given_label[-1] == '1':
                new_label = f"{old_generic_system_label}a"
            elif given_label[-1] == '2':
                new_label = f"{old_generic_system_label}b"
            else:
                raise Exception(f"During renaming leaf names: Unexpected leaf label {given_label}")
            main_bp.patch_node(leaf['leaf']['id'], {"label": new_label, "hostname": new_label })

    ########
    # create new generic systems
    # generic system data: generic_system_label.link.dict
    generic_systems_data = pull_generic_system(tor_bp, switch_label_pair)

    print(f"=== main: get generic_systems_data. {generic_systems_data=}")

    new_generic_systems(main_bp, generic_systems_data)

    update_generic_systems_lacp(main_bp, switch_label_pair, generic_systems_data)


    ########
    # assign virtual networks
    vn_list = tor_bp.query(f"node('system', name='system', role=not_in(['generic'])).out().node('vn_instance').out().node('virtual_network', name='vn')")
    # print(f"{vn_list=}")

    # assign connectivity templates



if __name__ == "__main__":
    import yaml

    with open('./tests/fixtures/config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    apstra = CkApstraSession("nf-apstra.pslab.link", 443, "admin", "zaq1@WSXcde3$RFV")
    main(apstra, config)

