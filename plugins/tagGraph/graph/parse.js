var network = null;

async function GQL(query, variables){
  return fetch("/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({query, variables})
  }).then(r => r.json())
}

async function getPluginConfig(pluginId){
  const query=`query FindPluginConfig($input: [String!]){ configuration { plugins (include: $input) } }`
  let config = await GQL(query, {"input": [pluginId]})
  try {
    return config.data.configuration.plugins[pluginId]  
  } catch (error) {
    return
  }
}

function parse(tags, excludeIds) {
    const nodes = []
    const edges = []
    for (const tag of tags) {
      if (excludeIds.includes(tag.id)){ continue; }
      nodes.push({
          id: tag.id,
          value: tag.scene_count,
          shape: "circularImage", // could also just use "image" here
          image: tag.image_path,
          label: tag.name
      })
      for (const child of tag.children) {
          edges.push({from:tag.id, to:child.id})
      }
    }
    return { nodes, edges }
}

async function getTags(tagFilter) {

  const query = `query FindTags($filter: FindFilterType, $tag_filter: TagFilterType) {
      findTags(filter: $filter, tag_filter: $tag_filter) {
              count
              tags {
                  id
                  name
                  image_path
                  scene_count
                  parents { id }
                  children { id }
              }
      }
  }`

  const variables = {
      "tag_filter": tagFilter,
      "filter": {"q": "", "per_page": -1},
  }

  return await GQL(query, variables) 
}

async function draw() {

  var pluginConfig = await getPluginConfig("tag-graph")

  var networkContainer = document.getElementById("taggraph");
  var optionsContainer = document.getElementById("graphoptions");

  var source = await getTags({
    "child_count": {"modifier": "GREATER_THAN", "value": 0},
      "OR":{
    "parent_count": {"modifier": "GREATER_THAN", "value": 0}}
  });

  if (source.data.findTags.count == 0){ alert("Could not find any tags with parent or sub tags, add parent or sub tags for them to show in the graph"); }
  console.log(`Found ${source.data.findTags.count} tags with parents/children`)

  if (Object.keys(excludeTagFilter).length !== 0){
    var exclude = await getTags(excludeTagFilter);
    excludeTagIDs = excludeTagIDs.concat(exclude.data.findTags.tags.map(t => t.id))
  }
  console.log(`Found ${excludeTagIDs.length} tags to exclude`)

  var data = parse(source.data.findTags.tags, excludeTagIDs)

  console.log(data)

  var options = {
    autoResize: true,
    height: `${window.screen.height}px`, //100% does not seem to work here
    width: "100%",
    configure: { 
      enabled: pluginConfig?.options, //set to true to enable config options 
      container: optionsContainer
    }, 
    nodes: {
      color: {
        border: "#adb5bd",
        background: "#394b59",
        highlight: {
          border: "#137cbd",
          background: "#FFFFFF"
        }
      },
      font: { color: "white" },
    },
    edges: {
      color: "#FFFFFF"
    },
    layout: {
      improvedLayout: false
    }
  };
  network = new vis.Network(networkContainer, data, options);
}