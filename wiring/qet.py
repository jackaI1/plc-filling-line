"""QElectroTech 0.9-compatible XML with self-contained pin symbols.

These are connection drawings: each row joins two explicitly identified device
pins. Repeated device references are pin views, not extra purchased devices.
"""
import xml.etree.ElementTree as ET
from uuid import NAMESPACE_URL, uuid5


def uid(text):
    return '{' + str(uuid5(NAMESPACE_URL, 'plc-filling-line/' + text)) + '}'


def write_qet(panel, path, title):
    project = ET.Element('project', title=title, version='0.90', uuid=uid(title))
    # Keep project portable: no dependency on an installed symbol collection.
    collection = ET.SubElement(project, 'collection')
    category = ET.SubElement(collection, 'category', name='panel')
    names = ET.SubElement(category, 'names')
    ET.SubElement(names, 'name', lang='en').text = 'Panel pin views'
    for side in ('left', 'right'):
        element = ET.SubElement(category, 'element', name=side + '.elmt')
        definition = ET.SubElement(element, 'definition', type='element', version='0.3',
                                   width='160', height='40', hotspot_x='80', hotspot_y='20', orientation='dyyy')
        names = ET.SubElement(definition, 'names')
        ET.SubElement(names, 'name', lang='en').text = side.title() + ' device pin'
        ET.SubElement(definition, 'informations').text = 'Jack Lai; MIT; connection-list pin view'
        desc = ET.SubElement(definition, 'description')
        ET.SubElement(desc, 'rect', x='-80', y='-20', width='160', height='40',
                      style='line-style:normal;line-weight:normal;filling:none;color:black')
        ET.SubElement(desc, 'input', x='-74', y='4', size='8', text='_', tagg='label')
        ET.SubElement(desc, 'terminal', x='80' if side == 'left' else '-80', y='0',
                      orientation='e' if side == 'left' else 'w')
    devices = {d['device']: d for d in panel['devices']}
    wires = panel['wires']
    # One folio per <=10 point-to-point runs, readable without routing crossings.
    for page, start in enumerate(range(0, len(wires), 10)):
        diagram = ET.SubElement(project, 'diagram', title=f'{title}: terminal wiring {page+1}',
                                version='0.90', uuid=uid(f'{title}/folio/{page}'), order=str(page),
                                cols='14', colsize='60', rows='8', rowsize='80', height='660',
                                displaycols='true', displayrows='true', author='Jack Lai', date='null',
                                folio='%id/%total', filename='')
        ET.SubElement(diagram, 'defaultconductor', type='multi', numsize='9')
        elements = ET.SubElement(diagram, 'elements')
        conductors = ET.SubElement(diagram, 'conductors')
        for row, wire in enumerate(wires[start:start+10]):
            y = 60 + row * 56
            ids = []
            for side, x, symbol in [('from', 170, 'left'), ('to', 650, 'right')]:
                tid = str((start + row) * 2 + len(ids))
                ids.append(tid)
                label = f"{wire[side+'_device']}:{wire[side+'_pin']}"
                element = ET.SubElement(elements, 'element', x=str(x), y=str(y), orientation='0',
                                        type=f'embed://panel/{symbol}.elmt', uuid=uid(f'{title}/{tid}'))
                terms = ET.SubElement(element, 'terminals')
                ET.SubElement(terms, 'terminal', id=tid, x='80' if symbol == 'left' else '-80',
                              y='0', orientation='1' if symbol == 'left' else '3')
                inputs = ET.SubElement(element, 'inputs')
                ET.SubElement(inputs, 'input', x='-74', y='4', text=label)
                texts = ET.SubElement(element, 'dynamic_texts')
                dynamic = ET.SubElement(texts, 'dynamic_elmt_text', x='-74', y='-8',
                                        text_from='UserText', text_width='-1', rotation='0',
                                        font='Arial,8,-1,5,50,0,0,0,0,0',
                                        uuid=uid(f'{title}/{tid}/label'),
                                        Halignment='AlignLeft', Valignment='AlignTop', frame='false')
                ET.SubElement(dynamic, 'text').text = label
                infos = ET.SubElement(element, 'elementInformations')
                ET.SubElement(infos, 'elementInformation', name='label', show='1').text = label
            conductor = ET.SubElement(conductors, 'conductor', terminal1=ids[0], terminal2=ids[1],
                                       type='multi', num=f"{wire['wire']}  {wire['gauge']} {wire['colour']}",
                                       numsize='8', displaytext='1', horizrotatetext='0', vertirotatetext='270',
                                       conductor_section=wire['gauge'], conductor_color=wire['colour'],
                                       condsize='1', text_color='#000000', color='#000000')
    # QET writes diagrams before collection; preserve this order for old readers.
    project.remove(collection)
    project.append(collection)
    ET.indent(project)
    ET.ElementTree(project).write(path, encoding='utf-8', xml_declaration=True)
