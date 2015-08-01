import collections
import dbm
import http.client
import io
import logging; log = logging.getLogger('qmsk.e2.presets')
import os
import os.path
import tarfile
import time
import urllib.error
import urllib.request

from xml.etree import ElementTree

class Error(Exception):
    pass

class XMLError(Error):
    pass

def parse_xml_inputcfg (xml):
    """
        <InputCfg>
            <Name>
    """

    index = int(xml.get('id'))
    title = xml.find('Name').text

    return ('inputs', index, {
        'title':        title,
    })

def parse_xml_stillmgr (xml):
    """
        <StillMgr>
            <Still>
                <Name>
    """

    for xml_still in xml.findall('Still'):
        index = int(xml_still.get('id'))
        title = xml_still.find('Name').text

        yield ('stills', index, {
            'title':    title,
        })

def parse_xml_aux_dest_index (xml):
    return (int(xml.find('OutCfgIndex').text), )

def parse_xml_aux_dest_sources (xml):
    aux_name = xml.find('Name').text
    
    for xml_source in xml.findall('Source'):
        source_name = xml_source.find('Name').text

        log.debug("%s: Source %s", aux_name, source_name)
        
        # XXX: wtf
        if int(xml_source.get('id')) != 1:
            continue

        xml_input_index = xml_source.find('InputCfgIndex')
        xml_still_index = xml_source.find('StillIndex')

        if xml_input_index is None:
            input_index = None
        elif xml_input_index.text == '-1':
            input_index = False
        else:
            input_index = int(xml_input_index.text)

            yield ('input', input_index, { })

        if xml_still_index is None :
            still_index = None
        elif xml_still_index.text == '-1':
            still_index = False
        else:
            still_index = int(xml_still_index.text)

            yield ('still', still_index, {})

def parse_xml_aux_dest (xml):
    """
        <AuxDest>
            <OutCfgIndex>
            <Name>
            <Source>
    """

    index = parse_xml_aux_dest_index(xml)
    # sources = list(parse_xml_aux_dest_sources(xml)) XXX

    return ('destinations', index, {
            'title':    xml.find('Name').text,
    })
    
def parse_xml_screen_dest_index (xml):
    """
        <ScreenDest>
            <DestOutMapCol><DestOutMap>
                <OutCfgIndex>
    """
    for xml_dest_out_map in xml.find('DestOutMapCol').findall('DestOutMap'):
        yield int(xml_dest_out_map.find('OutCfgIndex').text)

def parse_xml_screen_dest_sources (xml):
    """
        <ScreenDest>
            <LayerCollection><Layer>
                <PgmMode> <PvwMode>
                <LayerCfg><Source>
                    <InputCfgIndex>
                    <StillIndex>
    """

    name = xml.find('Name').text

    for xml_layer in xml.find('LayerCollection').findall('Layer'):
        xml_layer_name = xml_layer.find('Name')
        
        if xml_layer_name is None:
            layer_name = None
        else:
            layer_name = xml_layer_name.text

        xml_pgm_mode = xml_layer.find('PgmMode')
        xml_pvw_mode = xml_layer.find('PvwMode')
        
        if xml_pgm_mode is None:
            program = None
        else:
            program = bool(int(xml_pgm_mode.text))

        if xml_pvw_mode is None:
            preview = None
        else:
            preview = bool(int(xml_pvw_mode.text))
        
        if not (layer_name or program or preview):
            continue

        log.debug("%s: Layer %s program=%s preview=%s", name, layer_name, program, preview)
        
        for xml_source in xml_layer.find('LayerCfg').findall('Source'):
            source_name = xml_source.find('Name').text
        
            log.debug("%s: Layer %s: Source %s", name, layer_name, source_name)

            xml_input_index = xml_source.find('InputCfgIndex')
            xml_still_index = xml_source.find('StillIndex')

            if xml_input_index is None:
                input_index = None
            elif xml_input_index.text == '-1':
                input_index = False
            else:
                input_index = int(xml_input_index.text)

                yield ('input', input_index, preview, program)

            if xml_still_index is None:
                still_index = None
            elif xml_still_index.text == '-1':
                still_index = False
            else:
                still_index = int(xml_still_index.text)

                yield ('still', still_index, preview, program)

def parse_xml_screen_dest (xml):
    """
        <ScreenDest>
            <Name>
    """

    out_index = tuple(parse_xml_screen_dest_index(xml))

    preview_sources = set()
    program_sources = set()

    for source_type, source_index, source_preview, source_program in parse_xml_screen_dest_sources(xml):
        if source_preview:
            preview_sources.add((source_type, source_index))

        if source_program:
            program_sources.add((source_type, source_index))

    return ('destinations',     out_index, {
            'title':            xml.find('Name').text,
            'preview_sources':  preview_sources,
            'program_sources':  program_sources,
    })

def parse_xml_settings (xml):
    """
        <System>
            <DestMgr>
    """
    if xml.tag != 'System':
        raise XMLError("Unexpected preset root node: {xml}".format(xml=xml))

    xml_dest_mgr = xml.find('DestMgr')

    for xml_source in xml.find('SrcMgr').find('InputCfgCol').findall('InputCfg'):
       yield parse_xml_inputcfg(xml_source)

    for xml_aux_dest_col in xml_dest_mgr.findall('AuxDestCol'):
        for xml_aux_dest in xml_aux_dest_col.findall('AuxDest'):
            yield parse_xml_aux_dest(xml_aux_dest)
    
    for xml_screen_dest_col in xml_dest_mgr.findall('ScreenDestCol'):
        for xml_screen_dest in xml_screen_dest_col.findall('ScreenDest'):
            yield parse_xml_screen_dest(xml_screen_dest)

def parse_xml_preset (xml):
    """
        Parse XML dump <Preset> and return { }
    """
    
    preset_sno = xml.find('presetSno')
    if preset_sno is None:
        index = 0, (int(xml.attrib['id']) + 1)
    else:
        # new major.minor preset ID
        index_1, index_2 = preset_sno.text.split('.')

        index = (int(index_1), int(index_2))

    title = xml.find('Name').text
    destinations = collections.defaultdict(set)

    if '@' in title:
        title, group = title.split('@')
        title = title.strip()
        group = group.strip()
    else:
        group = None
    
    for xml_screen_dest_col in xml.findall('ScreenDestCol'):
        for xml_screen_dest in xml_screen_dest_col.findall('ScreenDest'):
            destination_title = xml_screen_dest.find('Name').text
            destination_index = tuple(parse_xml_screen_dest_index(xml_screen_dest))

            for source_type, source_index, source_preview, source_program in parse_xml_screen_dest_sources(xml_screen_dest):
                if source_program:
                    log.warning("%s %s: Ignore program sources for destination %s: %s:%s", index, title, destination_title, source_type, source_index)
                
                if source_preview:
                    log.debug("%s %s: Destination %s: Source %s:%s", index, title, destination_title, source_type, source_index)

                    destinations[destination_index].add((source_type, source_index))
        
    for xml_aux_dest_col in xml.findall('AuxDestCol'):
        for xml_aux_dest in xml_aux_dest_col.findall('AuxDest'):
            destination_index = tuple(parse_xml_aux_dest_index(xml_aux_dest))
            
            # XXX: aux sources
            destinations[destination_index] = []

    return ('presets', index, {
            'group': group,
            'destinations': destinations,
            'title': title,
    })

def parse_xml_presets (xml):
    """
        Load an XML dump <PresetMgr> root element and load the <Preset>s
    """

    if xml.tag != 'PresetMgr':
        raise XMLError("Unexpected preset root node: {xml}".format(xml=xml))
    
    for xml_preset in xml.findall('Preset'):
        yield parse_xml_preset(xml_preset)

def load_xml_file (file):
    """
        Load XML from  file object
    """

    return ElementTree.parse(file).getroot()

def load_xml_tar (xml_path, stream=False):
    """
        Load XML from E2Backup.tar.gz
    """


    if stream:
        mode = 'r|gz'
    else:
        mode = 'r:gz' # file supports seek

    log.info("Load tarfile: %s mode=%s", xml_path, mode)

    tar = tarfile.open(mode=mode, fileobj=xml_path)

    xml_settings_file = None
    xml_presets_files = []
    xml_still_files = []

    for path in tar.getnames():
        parts = os.path.normpath(path).split('/')

        if parts == ['xml', 'settings_backup.xml']:
            log.info("Load tarfile settings file: %s", path)

            xml_settings_file = load_xml_file(tar.extractfile(path))
            
        elif parts[0:2] == ['xml', 'presets'] and len(parts) == 3 and parts[2].endswith('.xml'):
            log.info("Load tarfile preset file: %s", path)

            xml_presets_files.append(load_xml_file(tar.extractfile(path)))

        elif parts[0:2] == ['xml', 'stills'] and len(parts) == 3 and parts[2].endswith('.xml'):
            log.info("Load tarfile still file: %s", path)

            xml_still_files.append(load_xml_file(tar.extractfile(path)))

        else:
            log.info("Skip tarfile: %s", '/'.join(parts))

    return xml_settings_file, xml_presets_files, xml_still_files

def load_xml_http (xml_path):
    """
        Load XML from http://192.168.0.x/backup-download
    """

    log.info("Load XML from network: %s", xml_path)
    
    while True:
        try:
            http_file = urllib.request.urlopen(xml_path)
        except (http.client.BadStatusLine, urllib.error.HTTPError) as error:
            log.exception("Retry XML from network")
        else:
            break
        
        # retry...
        time.sleep(2.0)
    
    # XXX: cannot extract a tarfile stream's members in-place
    xml_buf = io.BytesIO(http_file.read())

    return load_xml_tar(xml_buf)

def parse_xml (xml_path):
    """
        Yield (type, id, **attrs) loaded from XML tree (http://.../ url to download .tar.gz, path to E2Backup.tar.gz file, or extracted directory tree)
    """

    # settings
    if xml_path.startswith('http://'):
        xml_settings, xml_presets = load_xml_http(xml_path)

    elif os.path.isdir(xml_path):
        xml_presets_path = os.path.join(xml_path, 'presets')
        xml_stills_path = os.path.join(xml_path, 'stills')

        xml_settings = load_xml_file(open(os.path.join(xml_path, 'settings_backup.xml')))
        xml_presets = [
                load_xml_file(open(os.path.join(xml_presets_path, name))) 
                for name in os.listdir(xml_presets_path) if name.endswith('.xml')
        ]
        xml_stills = [
                load_xml_file(open(os.path.join(xml_stills_path, name))) 
                for name in os.listdir(xml_stills_path) if name.endswith('.xml')
        ]
    
    elif xml_path.endswith('.tar.gz'):
        xml_settings, xml_presets, xml_stills = load_xml_tar(open(xml_path, 'rb'))

    else:
        raise XMLError("Unknown xml path: %s" % (xml_path, ))

    # top-level
    if xml_settings:
        log.debug("%s", xml_settings)

        yield from parse_xml_settings(xml_settings)
    else:
        raise XMLError("Missing xml_settings.xml file")
    
    # stills
    for xml_stillmgr in xml_stills:
        log.debug("%s", xml_stillmgr)

        yield from parse_xml_stillmgr(xml_stillmgr)

    # presets
    for xml_preset in xml_presets:
        log.debug("%s", xml_preset)

        yield from parse_xml_presets(xml_preset)

class Source:
    pass

class Input(Source):
    """
        External input, used as a source for destination mixer layers.
    """

    def __init__ (self, index, *, title):
        self.index = index
        self.title = title

    def __str__ (self):
        return "{self.title}".format(self=self)

class Still(Source):
    """
        Still capture, used as a source for destination mixer layers.
    """

    def __init__ (self, index, *, title):
        self.index = index
        self.title = title

    def __str__ (self):
        return "{self.title}".format(self=self)

class Destination:
    """
        index:int                   destination index
        title:string                human-readable
        preview_preset:Preset       active preset on preview or None
        program_preset:Preset       active preset on program or None
    """

    def __init__ (self, index, preview_sources, program_sources, *, title):
        self.index = index

        self.title = title
        
        # active Presets
        self.preview_preset = None
        self.program_preset = None

        self.preview_sources = preview_sources
        self.program_sources = program_sources

    def __lt__ (self, preset):
        return self.title < preset.title 
   
    def __str__ (self):
        return "{self.title}".format(self=self)

class Preset:
    """
        _index:(int, int)               E2's internal preset ID
                                        old presets will use (0, id)
                                        new ordered presets will use (X, Y) with X > 0

        group:Group                             grouped presets
        destinations:{Destination: [Source]}    Destinations included in this preset
        title:string                            human-readable title
    """
    def __init__ (self, index, group, destinations, *, title):
        self._index = index
        self.group = group
        self.destinations = destinations

        self.title = title

    @property
    def index (self):
        """
            Index in string form, as used in the E2
        """

        if self._index[0] > 0:
            return '%d.%d' % self._index
        else:
            return '%d' % self._index[1]

    def __lt__ (self, preset):
        # sort using index major.minor ordering
        return self._index < preset._index

    def __str__ (self):
        return "{self.title} @ {self.group}".format(self=self)

class Group:
    def __init__ (self, index, *, title):
        self.index = index
        
        self.title = title
        self._presets = []

    def _add_preset (self, preset):
        self._presets.append(preset)

    @property
    def presets (self):
        return tuple(sorted(self._presets))

    def __str__ (self):
        if self.title is None:
            return "Ungrouped"
        else: 
            return self.title

class DBProperty:
    def __init__ (self, name):
        self.name = name

    def __get__ (self, obj, type=None):
        log.debug("%s", self.name)

        return obj.db.get(self.name)

    def __set__ (self, obj, value):
        log.debug("%s: %s", self.name, value)

        obj.db[self.name] = value

    def __del__ (self, obj):
        log.debug("%s", self.name)

        del obj.db[self.name]

class DB:
    def __init__(self, db, dump, load):
        self.db = db
        self.dump = dump
        self.load = load

    def key(self, key):
        if not isinstance(key, tuple):
            key = (key, )
        
        return '/'.join(str(k) for k in key)

    def __getitem__ (self, key):
        return self.load(self.db[self.key(key)])

    def get(self, *key):
        value = self.db.get(self.key(key))

        if value:
            return self.load(value)
        else:
            return None

    def __setitem__ (self, key, value):
        self.db[self.key(key)] = self.dump(value)

class Presets:
    """
        Load the Encore2 Presets database and implement a state machine for recalling/transitioning Presets.
    """

    @classmethod
    def load (cls, xml_path, db=None):
        data = collections.defaultdict(lambda: collections.defaultdict(list))
    
        for type, index, item in parse_xml(xml_path):
            log.debug("%s @ %s = %s", type, index, item)

            items = data[type]

            if index in items:
                raise XMLError("Duplicate {type}: {index}: {item}".format(type=type, index=index, item=item))

            items[index] = item

        if db:
            log.debug("%s", db)

            db = dbm.open(db, 'c')

        return cls(db, **data)

    def __init__ (self, db, inputs, stills, destinations, presets):
        self._sources = { }
        self._destinations = { }
        self._presets = { }

        self._groups = { }
        self.default_group = Group(None, title=None)

        # load
        for index, item in inputs.items():
            self._load_input(index, **item)
        
        for index, item in stills.items():
            self._load_still(index, **item)

        for index, item in destinations.items():
            self._load_destination(index, **item)

        for index, item in presets.items():
            self._load_preset(index, **item)

        # state
        self.db = db
        self.db_presets = DB(db,
                load    = lambda index: self._presets[index.decode('ascii')],
                dump    = lambda preset: preset.index,
        )

        self.active_preset = self.db_presets.get('active')

        log.info("Active preset: %s", self.active_preset)

        for destination in self._destinations.values():
            destination.preview_preset = self.db_presets.get('preview', destination.index)
            destination.program_preset = self.db_presets.get('program', destination.index)

        # events
        self._notify = set()

    def _load_input (self, index, **attrs):
        obj = self._sources['input', index] = Input(index, **attrs)
        
        log.info("%s: %s", index, obj)

        return obj

    def _load_still (self, index, **attrs):
        obj = self._sources['still', index] = Still(index, **attrs)
        
        log.info("%s: %s", index, obj)

        return obj

    def _load_destination (self, index, preview_sources=None, program_sources=None, **attrs):
        if preview_sources:
            preview_sources = [self._sources[sid] for sid in preview_sources] 
        else:
            preview_sources = []

        if program_sources:
            program_sources = [self._sources[sid] for sid in program_sources] 
        else:
            program_sources = []

        log.info("%s: %s <- preview=%s program=%s", index, attrs.get('title'),
                [str(source) for source in preview_sources],
                [str(source) for source in program_sources],
        )

        destination = Destination(index, preview_sources, program_sources, **attrs)

        self._destinations[index] = destination

        return destination

    def _load_group (self, title):
        index = title.lower()

        group = self._groups.get(index)

        if group is None:
            log.info("%s: %s", index, title)

            group = self._groups[index] = Group(index, title=title)
        
        return group


    def _load_preset (self, index, group=None, destinations={}, **item):
        """
            Load the given series of { 'preset': int, **opts } into (unique) Preset items.

                preset: int
                group: Group
        """

        log.info("%s: %s @ %s -> %s", index,
                item.get('title'),
                group,
                ' '.join('%s(%s)' % ('+'.join(str(o) for o in dest), ' '.join('%s:%s' % sid for sid in sources)) for dest, sources in destinations.items()),
        )

        if index in self._presets:
            raise Error("Duplicate preset: {index} = {item}".format(index=index, item=item))

        if group:
            group = self._load_group(group)
        else:
            group = self.default_group

        destinations = {self._destinations[index]: [self._sources[sid] for sid in sources] for index, sources in destinations.items()}
        
        preset = Preset(index, group=group, destinations=destinations, **item)
        self._presets[preset.index] = preset # in str format

        group._add_preset(preset)

        return preset

    # events
    def add_notify(self, func):
        log.info("%s", func)

        self._notify.add(func)

    def del_notify(self, func):
        log.info("%s", func)

        self._notify.remove(func)

    def notify(self):
        log.info("")

        for func in self._notify:
            try:
                func()
            except Exception as error:
                log.exception("%s: %s", func, error)

    # state
    def activate_preview (self, preset):
        """
            Activate the given preset. Updates the preview for the preset's destinations, and the active preset for activate_program().

            Returns the active preset, or None if unknown.
        """

        self.active_preset = self.db_presets['active'] = preset

        for destination in preset.destinations:
            log.info("%s: %s -> %s", destination, destination.preview_preset, preset)

            destination.preview_preset = self.db_presets['preview', destination.index] = preset
    
        self.notify()

        return preset

    def activate_program (self):
        """
            Take the currently active preset (from activate_preview(preset)) to program for its destinations.
            The currently active preset remains active.
        """

        preset = self.active_preset
        
        for destination in preset.destinations:
            log.info("%s: %s -> %s", destination, destination.program_preset, preset)

            destination.program_preset = self.db_presets['program', destination.index] = preset
        
        self.notify()

        return preset
 
    def close(self):
        if self.db:
            self.db.close()
   
    # query
    @property
    def groups (self):
        yield self.default_group

        for name, group in sorted(self._groups.items()):
            yield group

    @property
    def destinations (self):
        for name, obj in sorted(self._destinations.items()):
            yield obj

    def __iter__ (self):
        for preset in self._presets.values():
            yield preset

    def __getitem__ (self, key):
        return self._presets[key]

    def __len__ (self):
        return len(self._presets)

import argparse

def parser (parser):
    group = parser.add_argument_group("qmsk.e2.presets Options")
    group.add_argument('--e2-presets-xml', metavar='PATH',
            help="Load XML presets from http://.../backup-download url, E2Backup.tar.gz, or extracted dump directory")
    group.add_argument('--e2-presets-db', metavar='PATH',
        help="Store preset state in db")

def apply (args):
    presets = Presets.load(
        xml_path    = args.e2_presets_xml,
        db          = args.e2_presets_db,
    )

    return presets

